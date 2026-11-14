import SwiftUI
import BestBallKit

struct SetupView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Sleeper username", text: $model.username)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .submitLabel(.search)
                        .onSubmit { Task { await model.connect() } }
                } header: {
                    Text("Your Sleeper account")
                } footer: {
                    Text("Leagues for the \(String(model.currentSeason)) NFL season are loaded straight from Sleeper. Nothing is stored on a server.")
                }

                if model.isConnecting {
                    Section {
                        HStack(spacing: 12) {
                            ProgressView()
                            Text("Finding your leagues…")
                                .foregroundStyle(.secondary)
                        }
                    }
                } else if !model.leagues.isEmpty {
                    Section("Choose a league") {
                        ForEach(model.leagues) { league in
                            Button {
                                Task { await model.selectLeague(league) }
                            } label: {
                                LeagueRow(league: league)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                } else {
                    Section {
                        Button {
                            Task { await model.connect() }
                        } label: {
                            Label("Connect", systemImage: "arrow.right.circle.fill")
                        }
                        .disabled(model.username.trimmingCharacters(in: .whitespaces).isEmpty)
                    }
                }

                if let setupError = model.setupError {
                    Section {
                        Text(setupError)
                            .font(.callout)
                            .foregroundStyle(.red)
                    }
                }

                Section {
                    VStack(alignment: .leading, spacing: 8) {
                        Label("Optimistic projections", systemImage: "sparkles")
                            .font(.subheadline.weight(.semibold))
                        Text("Each player's projection assumes the rest of their game goes exactly as projected, on top of what they've already scored — and your lineup is filled best-ball style, so the highest projection always starts.")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 4)
                }
            }
            .navigationTitle("Best Ball")
            .scrollDismissesKeyboard(.interactively)
        }
    }
}
