import SwiftUI

@main
struct PMCommanderApp: App {
    @StateObject private var settings = AppSettings()
    @StateObject private var dashboard = DashboardViewModel()

    var body: some Scene {
        WindowGroup("Sapphire Operator Client") {
            ContentView()
                .environmentObject(settings)
                .environmentObject(dashboard)
                .task {
                    await dashboard.start(settings: settings)
                }
        }
        .defaultSize(width: 1260, height: 820)
    }
}
