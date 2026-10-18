import AppKit

// A synthetic acceptance target. Contains no accounts, network access or user data.
final class Fixture: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    let count = NSTextField(labelWithString: "count:0")
    var value = 0
    func applicationDidFinishLaunching(_ notification: Notification) {
        window = NSWindow(contentRect: NSRect(x: 180, y: 180, width: 360, height: 180),
                          styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.title = "Crewloom Native Acceptance"
        let increment = NSButton(title: "Increment", target: self, action: #selector(add))
        let reset = NSButton(title: "Reset", target: self, action: #selector(clear))
        let stack = NSStackView(views: [count, increment, reset])
        stack.orientation = .vertical
        stack.spacing = 14
        stack.translatesAutoresizingMaskIntoConstraints = false
        window.contentView!.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.centerXAnchor.constraint(equalTo: window.contentView!.centerXAnchor),
            stack.centerYAnchor.constraint(equalTo: window.contentView!.centerYAnchor)])
        window.orderBack(nil)
    }
    @objc func add() { value += 1; count.stringValue = "count:\(value)" }
    @objc func clear() { value = 0; count.stringValue = "count:0" }
}
let app = NSApplication.shared
let delegate = Fixture()
app.setActivationPolicy(.regular)
app.delegate = delegate
app.run()
