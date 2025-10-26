import SwiftUI

struct MatchupView: View {
    @State private var matchup: Matchup?
    @State private var isLoading = true
    @State private var error: String?
    let service = MatchupService()
    
    var body: some View {
        NavigationView {
            Group {
                if isLoading {
                    ProgressView("Loading matchup…")
                } else if let matchup = matchup {
                    VStack(spacing: 32) {
                        HStack {
                            VStack {
                                Text(matchup.teamA)
                                    .font(.headline)
                                Text("\(matchup.scoreA, specifier: \"%.2f\")")
                                    .font(.largeTitle)
                            }
                            Spacer()
                            Text("vs")
                                .font(.title)
                            Spacer()
                            VStack {
                                Text(matchup.teamB)
                                    .font(.headline)
                                Text("\(matchup.scoreB, specifier: \"%.2f\")")
                                    .font(.largeTitle)
                            }
                        }
                        .padding()
                    }
                } else if let error = error {
                    Text("Failed to load: \(error)")
                        .foregroundColor(.red)
                }
            }
            .onAppear(perform: loadMatchup)
            .navigationTitle("Current Matchup")
        }
    }
    
    private func loadMatchup() {
        isLoading = true
        error = nil
        service.fetchMatchup { result in
            DispatchQueue.main.async {
                isLoading = false
                switch result {
                case .success(let m):
                    matchup = m
                case .failure(let e):
                    error = e.localizedDescription
                }
            }
        }
    }
}

struct MatchupView_Previews: PreviewProvider {
    static var previews: some View {
        MatchupView()
    }
}