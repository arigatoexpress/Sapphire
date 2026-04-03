import SwiftUI

@main
struct SapphireCommandApp: App {
    @StateObject private var state = AppState()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(state)
                .frame(minWidth: 1100, minHeight: 700)
        }
        .windowStyle(.titleBar)
        .defaultSize(width: 1200, height: 800)

        MenuBarExtra("Sapphire OS", systemImage: "diamond.fill") {
            Button("Open Dashboard") {
                NSApp.activate(ignoringOtherApps: true)
            }
            Divider()
            Button("Quick Status") { Task { await state.refreshAll() } }
            Button("Run Factory Scan") { Task { await state.runFactoryScan() } }
            Divider()
            Button("Quit") { NSApp.terminate(nil) }
        }
    }
}
