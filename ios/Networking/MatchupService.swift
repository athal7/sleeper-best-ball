import Foundation

class MatchupService {
    func fetchMatchup(completion: @escaping (Result<Matchup, Error>) -> Void) {
        let url = URL(string: "https://your-api-here.com/matchup")!

        URLSession.shared.dataTask(with: url) { data, _, error in
            if let error = error {
                completion(.failure(error))
                return
            }
            guard let data = data else {
                completion(.failure(NSError(domain: "No data", code: -1)))
                return
            }
            do {
                let matchup = try JSONDecoder().decode(Matchup.self, from: data)
                completion(.success(matchup))
            } catch {
                completion(.failure(error))
            }
        }.resume()
    }
}