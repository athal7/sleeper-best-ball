/* The Rust engine's C boundary. Implemented in `core/src/abi.rs`; linked into
 * BestBallKit as `libbestball_engine.a` (see core/scripts/build-ios.sh). */
#ifndef BESTBALL_ENGINE_H
#define BESTBALL_ENGINE_H

/* Handles one JSON request and returns a JSON response the caller owns.
 * Free it with bestball_string_free. */
char *bestball_request(const char *input);

void bestball_string_free(char *pointer);

#endif /* BESTBALL_ENGINE_H */
