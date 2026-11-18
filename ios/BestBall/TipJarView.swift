import SwiftUI
import StoreKit

/// Tip jar: three consumable in-app purchases that say thanks and unlock
/// nothing. Products live in App Store Connect under these identifiers, so a
/// build that hasn't had them created shows the "unavailable" note instead of
/// failing.
struct TipJarView: View {
    @Environment(\.dismiss) private var dismiss

    private enum LoadState {
        case loading
        case ready([Product])
        case unavailable
    }

    @State private var state: LoadState = .loading
    @State private var purchasingID: String?
    @State private var message: String?

    /// Product identifiers, keyed to whatever bundle id this build signs with so
    /// a renamed copy doesn't look for someone else's products.
    static var productIDs: [String] {
        let bundle = Bundle.main.bundleIdentifier ?? "com.sleeperbestball.app"
        return ["\(bundle).tip.small", "\(bundle).tip.medium", "\(bundle).tip.large"]
    }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Thanks for using Sleeper Best Ball")
                            .font(.headline)
                        Text("It's free, has no ads, and has no account to pay for. If it's earned a place on your Home Screen, a tip keeps it maintained — and buys nothing else, on purpose.")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 4)
                }

                switch state {
                case .loading:
                    Section {
                        HStack(spacing: 12) {
                            ProgressView()
                            Text("Loading tips…")
                                .foregroundStyle(.secondary)
                        }
                    }

                case .ready(let products):
                    Section {
                        ForEach(products, id: \.id) { product in
                            Button {
                                Task { await buy(product) }
                            } label: {
                                HStack {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(product.displayName)
                                            .foregroundStyle(.primary)
                                        if !product.description.isEmpty {
                                            Text(product.description)
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                        }
                                    }
                                    Spacer(minLength: 8)
                                    if purchasingID == product.id {
                                        ProgressView()
                                    } else {
                                        Text(product.displayPrice)
                                            .font(.callout.weight(.semibold))
                                    }
                                }
                            }
                            .disabled(purchasingID != nil)
                        }
                    } footer: {
                        if let message {
                            Text(message)
                        } else {
                            Text("Tips are consumable purchases handled by the App Store. They unlock nothing and can be sent as often as you like.")
                        }
                    }

                case .unavailable:
                    Section {
                        VStack(alignment: .leading, spacing: 6) {
                            Label("Tips aren't available in this build", systemImage: "heart.slash")
                                .font(.subheadline.weight(.semibold))
                            Text("The tip products aren't published for this bundle identifier yet, which is normal for a build installed straight from Xcode.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .padding(.vertical, 4)
                    }
                }
            }
            .navigationTitle("Send a tip")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
            .task { await load() }
        }
    }

    private func load() async {
        do {
            let products = try await Product.products(for: Self.productIDs)
            let sorted = products.sorted { $0.price < $1.price }
            state = sorted.isEmpty ? .unavailable : .ready(sorted)
        } catch {
            state = .unavailable
        }
    }

    private func buy(_ product: Product) async {
        purchasingID = product.id
        defer { purchasingID = nil }
        do {
            let result = try await product.purchase()
            switch result {
            case .success(let verification):
                switch verification {
                case .verified(let transaction):
                    await transaction.finish()
                    message = "Thank you — tip received."
                case .unverified:
                    message = "The App Store couldn't verify that purchase, so nothing was charged."
                }
            case .userCancelled:
                break
            case .pending:
                message = "That purchase is pending approval. It completes on its own once approved."
            @unknown default:
                break
            }
        } catch {
            message = "The purchase didn't go through: \(error.localizedDescription)"
        }
    }
}
