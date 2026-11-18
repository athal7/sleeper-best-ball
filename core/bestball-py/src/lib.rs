//! Python surface: the `bestball_core` extension module.
//!
//! Built with `maturin build --features python` and imported by
//! `streamlit_app.py`. Trades are scored by the same code the iOS app links,
//! not by a second implementation that has to be kept in step.

use std::collections::HashMap;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use bestball_engine::lineup;
use bestball_engine::slots::slots_for;
use bestball_engine::uplift::{self as uplift_model, Candidate, UpliftInput};

fn starting_slots(slot_positions: &[String]) -> Vec<bestball_engine::slots::Slot> {
    slots_for(slot_positions)
        .into_iter()
        .filter(|slot| !slot.is_bench())
        .collect()
}

/// Best-lineup total for the starters, plus each player's slot label.
///
/// `players` is `(id, position, score)`. `slot_positions` is a league's
/// `roster_positions` (bench and IR entries included; both are ignored here).
#[pyfunction]
fn best_lineup_score(
    slot_positions: Vec<String>,
    players: Vec<(String, String, f64)>,
) -> PyResult<(f64, HashMap<String, String>)> {
    let slots = starting_slots(&slot_positions);
    let positions: Vec<&str> = players.iter().map(|(_, position, _)| position.as_str()).collect();
    let scores: Vec<f64> = players.iter().map(|(_, _, score)| *score).collect();
    let assignment = lineup::assign(&positions, &scores, &slots);

    let mut labelled = HashMap::new();
    let mut total = 0.0;
    for (index, slot_index) in assignment.iter().enumerate() {
        let Some(slot_index) = slot_index else {
            continue;
        };
        let slot = &slots[*slot_index];
        if slot.is_bench() {
            continue;
        }
        total += scores[index];
        labelled.insert(players[index].0.clone(), slot.label.clone());
    }
    Ok((total, labelled))
}

/// Lineup uplift per candidate, averaged over weeks with playoff weighting.
///
/// `weekly` lists are 0-based: element 0 is week 1. `roster` and `candidates`
/// are `(id, position, weekly)`.
#[pyfunction]
#[pyo3(signature = (slot_positions, roster, candidates, weeks, playoff_week_start=None))]
fn lineup_uplift(
    slot_positions: Vec<String>,
    roster: Vec<(String, String, Vec<f64>)>,
    candidates: Vec<(String, String, Vec<f64>)>,
    weeks: usize,
    playoff_week_start: Option<usize>,
) -> PyResult<HashMap<String, f64>> {
    if weeks == 0 {
        return Ok(HashMap::new());
    }
    if roster.iter().any(|(_, _, weekly)| weekly.len() < weeks)
        || candidates.iter().any(|(_, _, weekly)| weekly.len() < weeks)
    {
        return Err(PyValueError::new_err(
            "every player needs at least `weeks` weekly scores",
        ));
    }

    let slots = starting_slots(&slot_positions);
    let roster_positions: Vec<&str> = roster.iter().map(|(_, position, _)| position.as_str()).collect();
    // The engine indexes weeks from 1; the Python side is 0-based.
    let roster_weekly: Vec<Vec<f64>> = roster
        .iter()
        .map(|(_, _, weekly)| once_padded(weekly))
        .collect();
    let padded: Vec<Vec<f64>> = candidates
        .iter()
        .map(|(_, _, weekly)| once_padded(weekly))
        .collect();
    let candidate_inputs: Vec<Candidate> = candidates
        .iter()
        .enumerate()
        .map(|(index, (_, position, _))| Candidate {
            position: position.as_str(),
            weekly: &padded[index],
        })
        .collect();

    let values = uplift_model::lineup_uplift(&UpliftInput {
        slots: &slots,
        roster_positions: &roster_positions,
        roster_weekly: &roster_weekly,
        candidates: &candidate_inputs,
        playoff_week_start,
        weeks,
    });

    Ok(candidates
        .iter()
        .enumerate()
        .map(|(index, (id, _, _))| (id.clone(), values[index]))
        .collect())
}

fn once_padded(weekly: &[f64]) -> Vec<f64> {
    let mut padded = Vec::with_capacity(weekly.len() + 1);
    padded.push(0.0);
    padded.extend_from_slice(weekly);
    padded
}

#[pymodule]
fn bestball_core(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(best_lineup_score, module)?)?;
    module.add_function(wrap_pyfunction!(lineup_uplift, module)?)?;
    module.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
