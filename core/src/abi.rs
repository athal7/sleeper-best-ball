//! JSON-over-C boundary shared by both shells.
//!
//! Swift links the static library and calls these `extern "C"` symbols; Python
//! loads the dylib with `ctypes`. One request in, one response out, both JSON:
//! cheap enough for a lineup pass and stable enough that neither shell needs to
//! know the engine's internal types.
//!
//! Requests carry raw league inputs (`slot_positions` is a league's
//! `roster_positions`, bench and IR included). The engine owns the slot table,
//! so shells never re-implement slot expansion.

use std::collections::BTreeMap;
use std::ffi::{c_char, CStr, CString};
use std::panic::{catch_unwind, AssertUnwindSafe};

use serde::{Deserialize, Serialize};

use crate::lineup;
use crate::slots::slots_for;
use crate::uplift::{self, Candidate, UpliftInput};

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PlayerInput {
    pub id: String,
    pub position: String,
    pub score: f64,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub op: String,
    #[serde(default)]
    pub slot_positions: Vec<String>,
    #[serde(default)]
    pub players: Vec<PlayerInput>,
    /// Roster the candidate would join, for the uplift ops.
    #[serde(default)]
    pub roster: Vec<WeeklyPlayerInput>,
    /// Undrafted players being weighed.
    #[serde(default)]
    pub candidates: Vec<WeeklyPlayerInput>,
    #[serde(default)]
    pub playoff_week_start: Option<usize>,
    #[serde(default)]
    pub weeks: usize,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WeeklyPlayerInput {
    pub id: String,
    pub position: String,
    /// Points per week, 1-based to match the request's `weeks`.
    pub weekly: Vec<f64>,
}

#[derive(Debug, Serialize)]
pub struct UpliftResponse {
    pub uplift: BTreeMap<String, f64>,
}

#[derive(Debug, Serialize)]
pub struct LineupResponse {
    /// Total for the starters only.
    pub score: f64,
    /// Player id -> slot label, starters and bench.
    pub assignment: BTreeMap<String, String>,
}

#[derive(Debug, Serialize)]
pub struct ErrorResponse {
    pub error: String,
}

fn handle(request: Request) -> Result<serde_json::Value, String> {
    match request.op.as_str() {
        "best_lineup_score" => {
            let slots = slots_for(&request.slot_positions);
            let positions: Vec<&str> = request
                .players
                .iter()
                .map(|player| player.position.as_str())
                .collect();
            let scores: Vec<f64> = request.players.iter().map(|player| player.score).collect();
            let assignment = lineup::assign(&positions, &scores, &slots);

            let mut labelled = BTreeMap::new();
            for (index, slot_index) in assignment.iter().enumerate() {
                if let Some(slot_index) = slot_index {
                    labelled.insert(
                        request.players[index].id.clone(),
                        slots[*slot_index].label.clone(),
                    );
                }
            }
            let score = assignment
                .iter()
                .enumerate()
                .filter(|(_, slot_index)| match slot_index {
                    Some(index) => !slots[*index].is_bench(),
                    None => false,
                })
                .map(|(player, _)| scores[player])
                .sum();
            Ok(serde_json::to_value(LineupResponse {
                score,
                assignment: labelled,
            })
            .map_err(|error| error.to_string())?)
        }
        "lineup_uplift" => {
            let slots = slots_for(&request.slot_positions);
            let starting: Vec<_> = slots.iter().filter(|slot| !slot.is_bench()).cloned().collect();
            let roster_positions: Vec<&str> = request
                .roster
                .iter()
                .map(|player| player.position.as_str())
                .collect();
            let roster_weekly: Vec<Vec<f64>> =
                request.roster.iter().map(|player| player.weekly.clone()).collect();
            let candidates: Vec<Candidate> = request
                .candidates
                .iter()
                .map(|player| Candidate {
                    position: player.position.as_str(),
                    weekly: &player.weekly,
                })
                .collect();

            let values = uplift::lineup_uplift(&UpliftInput {
                slots: &starting,
                roster_positions: &roster_positions,
                roster_weekly: &roster_weekly,
                candidates: &candidates,
                playoff_week_start: request.playoff_week_start,
                weeks: request.weeks,
            });

            let mut result = BTreeMap::new();
            for (index, player) in request.candidates.iter().enumerate() {
                result.insert(player.id.clone(), values[index]);
            }
            Ok(serde_json::to_value(UpliftResponse { uplift: result })
                .map_err(|error| error.to_string())?)
        }
        other => Err(format!("unknown op: {other}")),
    }
}

fn respond(body: String) -> *mut c_char {
    match CString::new(body) {
        Ok(value) => value.into_raw(),
        // A NUL byte can only come from a player id; fail closed rather than
        // handing back a truncated string.
        Err(_) => CString::new(r#"{"error":"response contained a NUL byte"}"#)
            .expect("static string")
            .into_raw(),
    }
}

/// Handles one JSON request and returns a JSON response. Free the result with
/// `bestball_string_free`.
#[no_mangle]
pub extern "C" fn bestball_request(input: *const c_char) -> *mut c_char {
    if input.is_null() {
        return respond(r#"{"error":"null request"}"#.to_string());
    }
    let body = catch_unwind(AssertUnwindSafe(|| {
        // SAFETY: the shells only ever pass a NUL-terminated string they own.
        let raw = unsafe { CStr::from_ptr(input) };
        let text = match raw.to_str() {
            Ok(text) => text,
            Err(_) => return r#"{"error":"request was not utf-8"}"#.to_string(),
        };
        let request: Request = match serde_json::from_str(text) {
            Ok(request) => request,
            Err(error) => {
                return serde_json::json!({ "error": error.to_string() }).to_string();
            }
        };
        match handle(request) {
            Ok(response) => response.to_string(),
            Err(error) => serde_json::json!({ "error": error }).to_string(),
        }
    }));
    match body {
        Ok(body) => respond(body),
        Err(_) => respond(r#"{"error":"engine panicked"}"#.to_string()),
    }
}

/// Frees a string returned by `bestball_request`.
#[no_mangle]
pub extern "C" fn bestball_string_free(ptr: *mut c_char) {
    if ptr.is_null() {
        return;
    }
    // SAFETY: the pointer came from CString::into_raw in this module.
    unsafe {
        drop(CString::from_raw(ptr));
    }
}
