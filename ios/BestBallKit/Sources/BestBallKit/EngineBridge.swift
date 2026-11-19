import CEngine
import Foundation

/// JSON bridge to the Rust engine in `core/`, the same code the Streamlit app
/// runs through the `bestball_core` wheel.
///
/// Requests and responses are JSON over the C symbols in `core/src/abi.rs`.
/// Nothing here does arithmetic; it only moves values across the boundary, so
/// a change in scoring rules belongs in `core/` and lands in both apps at once.
enum EngineBridge {
    struct Player: Encodable {
        let id: String
        let position: String
        let score: Double
    }

    private struct LineupRequest: Encodable {
        let op = "best_lineup_score"
        let slot_positions: [String]
        let players: [Player]
    }

    private struct LineupResponse: Decodable {
        let score: Double
        let assignment: [String: String]
    }

    private struct ErrorResponse: Decodable {
        let error: String
    }

    /// Player id -> slot label for the best lineup, bench included.
    ///
    /// Returns an empty assignment if the engine rejects the request, which
    /// shows every player on the bench; loud in debug builds so a broken
    /// boundary cannot pass as a quiet zero.
    static func lineupAssignment(slotPositions: [String], players: [Player]) -> [String: String] {
        let request = LineupRequest(slot_positions: slotPositions, players: players)
        guard let response: LineupResponse = perform(request) else {
            assertionFailure("engine: best_lineup_score request failed")
            return [:]
        }
        return response.assignment
    }

    private static func perform<Request: Encodable, Response: Decodable>(
        _ request: Request
    ) -> Response? {
        guard let body = try? JSONEncoder().encode(request) else { return nil }
        guard let reply = send(body) else { return nil }
        let decoder = JSONDecoder()
        if let error = try? decoder.decode(ErrorResponse.self, from: reply) {
            assertionFailure("engine: \(error.error)")
            return nil
        }
        return try? decoder.decode(Response.self, from: reply)
    }

    /// One call across the C boundary; the engine owns the returned string.
    private static func send(_ request: Data) -> Data? {
        let json = String(decoding: request, as: UTF8.self)
        let pointer = json.withCString { bestball_request($0) }
        guard let pointer else { return nil }
        defer { bestball_string_free(pointer) }
        return Data(String(cString: pointer).utf8)
    }
}
