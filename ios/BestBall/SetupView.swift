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
                    Text("Every \(String(model.currentSeason)) NFL league you're in is loaded straight from Sleeper and shown on one screen. Nothing is stored on a server, and you only type your username once.")
                }

                if model.isConnecting {
                    Section {
                        HStack(spacing: 12) {
                            ProgressView()
                            Text("Loading every league you're in…")
                                .foregroundStyle(.secondary)
                        }
                    }
                } else {
                    Section {
                        Button {
                            Task { await model.connect() }
                        } label: {
                            Label("Show my scores", systemImage: "arrow.right.circle.fill")
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
