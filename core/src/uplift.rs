//! How much a candidate adds to a lineup, week by week.
//!
//! This is the value model behind both waivers and trades: a player's worth is
//! the lineup score they add to *this* roster, not their raw points. Bench
//! players add nothing, which is why a spare receiver is worth more to a team
//! with an open slot than to the team holding them.
//!
//! Port of `compute_lineup_uplift` in `streamlit_app.py`, with the same
//! playoff weighting: weeks at or after `playoff_week_start` count 1.5x.

use crate::lineup::best_lineup_score;
use crate::slots::Slot;

pub const PLAYOFF_WEIGHT: f64 = 1.5;

/// One undrafted player the caller is weighing.
pub struct Candidate<'a> {
    pub position: &'a str,
    /// Points per week, indexed from week 1 (index 0 is unused filler).
    pub weekly: &'a [f64],
}

pub struct UpliftInput<'a> {
    /// Starting slots only; bench slots would score nothing anyway.
    pub slots: &'a [Slot],
    /// Positions of the roster the candidate would join, one per player.
    pub roster_positions: &'a [&'a str],
    /// Weekly points for those roster players, same index order.
    pub roster_weekly: &'a [Vec<f64>],
    pub candidates: &'a [Candidate<'a>],
    /// First playoff week, 1-based. `None` means the season is not weighted.
    pub playoff_week_start: Option<usize>,
    /// Number of weeks to average over, starting at week 1.
    pub weeks: usize,
}

/// Per-candidate uplift, averaged over the weeks with playoff weighting applied.
pub fn lineup_uplift(input: &UpliftInput) -> Vec<f64> {
    let mut uplift = vec![0.0; input.candidates.len()];
    if input.weeks == 0 || input.slots.is_empty() {
        return uplift;
    }

    let mut total_weight = 0.0;
    for week in 1..=input.weeks {
        let weight = match input.playoff_week_start {
            Some(start) if week >= start => PLAYOFF_WEIGHT,
            _ => 1.0,
        };
        total_weight += weight;

        let roster_scores: Vec<f64> = input
            .roster_weekly
            .iter()
            .map(|weekly| weekly.get(week).copied().unwrap_or(0.0))
            .collect();
        let baseline = best_lineup_score(input.roster_positions, &roster_scores, input.slots);

        // Best lineup with each slot removed: what the candidate's slot is
        // currently worth, which differs per slot type.
        let without_slot: Vec<f64> = (0..input.slots.len())
            .map(|missing| {
                let remaining: Vec<Slot> = input
                    .slots
                    .iter()
                    .enumerate()
                    .filter(|(index, _)| *index != missing)
                    .map(|(_, slot)| slot.clone())
                    .collect();
                best_lineup_score(input.roster_positions, &roster_scores, &remaining)
            })
            .collect();

        // Only the best open slot of each type matters: adding a second tight
        // end is worth nothing when the first already fills TE1.
        for (index, candidate) in input.candidates.iter().enumerate() {
            let mut best_slot_value: Option<f64> = None;
            for (slot_index, slot) in input.slots.iter().enumerate() {
                if !slot.accepts(candidate.position) {
                    continue;
                }
                let value = without_slot[slot_index];
                best_slot_value = Some(match best_slot_value {
                    Some(current) if current > value => current,
                    _ => value,
                });
            }
            let Some(best_slot_value) = best_slot_value else {
                continue;
            };
            let candidate_score = candidate.weekly.get(week).copied().unwrap_or(0.0);
            uplift[index] += weight * (candidate_score + best_slot_value - baseline).max(0.0);
        }
    }

    let divisor = total_weight.max(1.0);
    for value in &mut uplift {
        *value /= divisor;
    }
    uplift
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::slots::slots_for;

    fn owned(values: &[&str]) -> Vec<String> {
        values.iter().map(|value| value.to_string()).collect()
    }

    #[test]
    fn playoff_weeks_count_more_than_regular_season_weeks() {
        let slots = slots_for(&owned(&["RB", "WR"]));
        let starting: Vec<Slot> = slots.into_iter().filter(|slot| !slot.is_bench()).collect();
        let roster_positions = ["RB"];
        let roster_weekly = vec![vec![0.0, 10.0, 10.0, 10.0, 10.0]];
        // Same receiver every week; only the week weighting differs.
        let candidate_weekly = [0.0, 1.0, 1.0, 10.0, 10.0];
        let candidates = [Candidate {
            position: "WR",
            weekly: &candidate_weekly,
        }];

        let flat = lineup_uplift(&UpliftInput {
            slots: &starting,
            roster_positions: &roster_positions,
            roster_weekly: &roster_weekly,
            candidates: &candidates,
            playoff_week_start: None,
            weeks: 4,
        });
        assert_eq!(flat[0], 5.5);

        let weighted = lineup_uplift(&UpliftInput {
            slots: &starting,
            roster_positions: &roster_positions,
            roster_weekly: &roster_weekly,
            candidates: &candidates,
            playoff_week_start: Some(3),
            weeks: 4,
        });
        // (1 + 1 + 1.5*10 + 1.5*10) / 5
        assert_eq!(weighted[0], 6.4);
    }

    #[test]
    fn a_bench_player_adds_nothing_until_a_slot_opens() {
        let slots = slots_for(&owned(&["RB", "WR"]));
        let starting: Vec<Slot> = slots.into_iter().filter(|slot| !slot.is_bench()).collect();
        // Both starting slots already filled.
        let roster_positions = ["RB", "WR"];
        let roster_weekly = vec![vec![0.0, 12.0], vec![0.0, 9.0]];
        let candidate_weekly = [0.0, 8.0];
        let candidates = [Candidate {
            position: "WR",
            weekly: &candidate_weekly,
        }];

        let uplift = lineup_uplift(&UpliftInput {
            slots: &starting,
            roster_positions: &roster_positions,
            roster_weekly: &roster_weekly,
            candidates: &candidates,
            playoff_week_start: None,
            weeks: 1,
        });
        assert_eq!(uplift[0], 0.0);
    }
}
