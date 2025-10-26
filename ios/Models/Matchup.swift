import Foundation

struct Matchup: Codable, Identifiable {
    var id: String {
        "\(teamA)-vs-\(teamB)"
    }
    let teamA: String
    let teamB: String
    let scoreA: Double
    let scoreB: Double
}