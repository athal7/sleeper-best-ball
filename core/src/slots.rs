//! Slot expansion and eligibility.
//!
//! Both shells used to carry their own copy of this table: `Positions.MAPPINGS`
//! in `streamlit_app.py` and `LineupSlots` in `BestBallKit`. It lives here now,
//! and the two shells only pass `roster_positions` strings through.

/// Slot expansion order. Anything not listed (`IR`, `TAXI`, ...) is ignored, so
/// an IR slot never scores.
pub const ORDER: [&str; 9] = [
    "QB", "RB", "WR", "TE", "FLEX", "SUPER_FLEX", "K", "DEF", "BN",
];

/// Positions a slot accepts. `None` means "not a slot we know about".
pub fn eligibility(position: &str) -> Option<&'static [&'static str]> {
    Some(match position {
        "QB" => &["QB"],
        "RB" => &["RB"],
        "WR" => &["WR"],
        "TE" => &["TE"],
        "FLEX" => &["RB", "WR", "TE"],
        "SUPER_FLEX" => &["QB", "RB", "WR", "TE"],
        "K" => &["K"],
        "DEF" => &["DEF"],
        "BN" => &["QB", "RB", "WR", "TE", "K", "DEF"],
        _ => return None,
    })
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Slot {
    /// Human label assigned to the starter, e.g. `RB2`.
    pub label: String,
    /// Slot type, e.g. `RB`.
    pub position: String,
    /// Positions that can fill it.
    pub eligible: Vec<String>,
}

impl Slot {
    pub fn is_bench(&self) -> bool {
        self.position == "BN"
    }

    pub fn accepts(&self, position: &str) -> bool {
        self.eligible.iter().any(|p| p == position)
    }
}

fn slot(position: &str, number: usize, eligible: &[&str]) -> Slot {
    Slot {
        label: format!("{position}{number}"),
        position: position.to_string(),
        eligible: eligible.iter().map(|p| p.to_string()).collect(),
    }
}

/// Expands a league's `roster_positions` into labelled slots.
///
/// Bench slots are included: callers that score a lineup drop them, callers
/// that lay out a roster keep them.
pub fn slots_for(roster_positions: &[String]) -> Vec<Slot> {
    let mut slots = Vec::new();
    for position in ORDER {
        let Some(eligible) = eligibility(position) else {
            continue;
        };
        let count = roster_positions.iter().filter(|p| *p == position).count();
        for number in 1..=count {
            slots.push(slot(position, number, eligible));
        }
    }
    slots
}

/// One slot per player in `positions`, each accepting only that position.
///
/// This is what `DraftSettings.from_actual_roster` produced and what the waiver
/// path still uses, kept so the two answers stay comparable.
pub fn roster_slots(positions: &[String]) -> Vec<Slot> {
    let mut order: Vec<&String> = Vec::new();
    let mut counts: std::collections::BTreeMap<&String, usize> = Default::default();
    for position in positions {
        if !counts.contains_key(position) {
            order.push(position);
        }
        *counts.entry(position).or_default() += 1;
    }
    let mut slots = Vec::new();
    for position in order {
        for number in 1..=counts[position] {
            slots.push(slot(position, number, &[position.as_str()]));
        }
    }
    slots
}
