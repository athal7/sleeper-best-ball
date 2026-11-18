//! Lineup selection and scoring.
//!
//! One greedy pass: players are ranked by score, slots are offered in priority
//! order (fixed slots first, then FLEX, then SUPER_FLEX, then bench), and each
//! slot takes the best remaining player it accepts. This is the same pass
//! `_best_lineup_score` in `streamlit_app.py` and `BestBallEngine.assignSlots`
//! in `BestBallKit` performed; keeping it in one place is the point of this
//! crate.

use crate::slots::Slot;

/// Fixed slots before flex slots before super flex before bench, so a receiver
/// does not get parked in FLEX while a WR slot sits empty.
pub fn priority(slot: &str) -> u8 {
    match slot {
        "QB" | "RB" | "WR" | "TE" | "K" | "DEF" => 1,
        "FLEX" | "FX" => 2,
        "SUPER_FLEX" | "SFX" => 3,
        _ => 4,
    }
}

/// Indices into `scores`, best first. Ties break on the original order so the
/// result never depends on sort stability.
fn ranking(scores: &[f64]) -> Vec<usize> {
    let mut order: Vec<usize> = (0..scores.len()).collect();
    order.sort_by(|a, b| {
        scores[*b]
            .partial_cmp(&scores[*a])
            .unwrap_or(std::cmp::Ordering::Equal)
            .then(a.cmp(b))
    });
    order
}

/// Slot indices in fill order: by priority, then as given.
fn slot_order(slots: &[Slot]) -> Vec<usize> {
    let mut order: Vec<usize> = (0..slots.len()).collect();
    order.sort_by(|a, b| {
        priority(&slots[*a].position)
            .cmp(&priority(&slots[*b].position))
            .then(a.cmp(b))
    });
    order
}

/// Assigns players to slots, returning `player index -> slot label`.
///
/// Unassigned players get no entry; callers decide how to label their bench.
pub fn assign(positions: &[&str], scores: &[f64], slots: &[Slot]) -> Vec<Option<usize>> {
    assert_eq!(positions.len(), scores.len(), "one position per score");
    let mut assignment: Vec<Option<usize>> = vec![None; positions.len()];
    let ranked = ranking(scores);
    let mut taken = vec![false; positions.len()];
    for slot_index in slot_order(slots) {
        let target = &slots[slot_index];
        for player in &ranked {
            if taken[*player] {
                continue;
            }
            if target.accepts(positions[*player]) {
                taken[*player] = true;
                assignment[*player] = Some(slot_index);
                break;
            }
        }
    }
    assignment
}

/// Total of the starters only: bench slots contribute nothing.
pub fn best_lineup_score(positions: &[&str], scores: &[f64], slots: &[Slot]) -> f64 {
    let assignment = assign(positions, scores, slots);
    let mut total = 0.0;
    for (player, slot_index) in assignment.iter().enumerate() {
        match slot_index {
            Some(index) if !slots[*index].is_bench() => total += scores[player],
            _ => {}
        }
    }
    total
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::slots::slots_for;

    fn owned(values: &[&str]) -> Vec<String> {
        values.iter().map(|value| value.to_string()).collect()
    }

    const LEAGUE: [&str; 6] = ["QB", "RB", "RB", "WR", "WR", "TE"];

    #[test]
    fn drops_bench_and_unknown_slots() {
        let slots = slots_for(&owned(&[
            "QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "BN", "BN", "BN", "IR",
        ]));
        let labels: Vec<&str> = slots.iter().map(|slot| slot.label.as_str()).collect();
        assert_eq!(
            labels,
            ["QB1", "RB1", "RB2", "WR1", "WR2", "TE1", "FLEX1", "BN1", "BN2", "BN3"]
        );
    }

    /// Same fixture as `leagueLineupFindsDealsTheRosterSlotFallbackMisses` in
    /// `BestBallKitTests` and
    /// `test_trades_use_the_league_lineup_not_the_users_own_roster_shape` in
    /// `tests/test_trade.py`: my side of that league.
    #[test]
    fn scores_the_league_lineup_not_the_roster_shape() {
        let slots = slots_for(&owned(&LEAGUE));
        let positions = ["QB", "RB", "RB", "WR", "WR", "WR"];
        let scores = [20.0, 15.0, 10.0, 20.0, 18.0, 12.0];

        // Every starting slot filled, no TE on the roster, so 20+15+10+20+18.
        assert_eq!(best_lineup_score(&positions, &scores, &slots), 83.0);

        // A bench receiver is worth nothing until a slot opens for them: three
        // receivers already compete for two WR slots, so a fourth changes
        // nothing.
        let with_receiver: Vec<f64> = scores.iter().copied().chain([12.0]).collect();
        let positions: Vec<&str> = positions.iter().copied().chain(["WR"]).collect();
        assert_eq!(best_lineup_score(&positions, &with_receiver, &slots), 83.0);

        // A tight end fills the empty TE slot on top of that: 83 + 15.
        let positions: Vec<&str> = positions.iter().copied().chain(["TE"]).collect();
        let with_tight_end: Vec<f64> = with_receiver.iter().copied().chain([15.0]).collect();
        assert_eq!(best_lineup_score(&positions, &with_tight_end, &slots), 98.0);
    }

    #[test]
    fn fills_fixed_slots_before_flex() {
        let slots = slots_for(&owned(&["WR", "WR", "FLEX"]));
        // Three receivers, one flex: the WR slots must take the best two.
        let positions = ["WR", "WR", "RB"];
        let scores = [10.0, 8.0, 20.0];
        let assignment = assign(&positions, &scores, &slots);

        assert_eq!(slots[assignment[0].unwrap()].label, "WR1");
        assert_eq!(slots[assignment[1].unwrap()].label, "WR2");
        assert_eq!(slots[assignment[2].unwrap()].label, "FLEX1");
        assert_eq!(best_lineup_score(&positions, &scores, &slots), 38.0);
    }

    #[test]
    fn bench_slots_accept_anyone_but_score_nothing() {
        let slots = slots_for(&owned(&["QB", "BN"]));
        let positions = ["QB", "RB"];
        let scores = [10.0, 30.0];
        assert_eq!(best_lineup_score(&positions, &scores, &slots), 10.0);
    }
}
