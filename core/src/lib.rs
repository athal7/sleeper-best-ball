//! Shared engine for the Best Ball iOS app and the Streamlit app.
//!
//! Everything here is platform-neutral: no HTTP, no threading, no UI, no
//! date/time formatting. The shells bring data in and render results out; the
//! arithmetic that decides what a trade or a waiver add is worth lives here so
//! both surfaces cannot drift apart.

pub mod abi;
pub mod lineup;
pub mod scoring;
pub mod slots;
pub mod uplift;
