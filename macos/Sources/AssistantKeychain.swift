// The assistant's provider API keys: kept in the login Keychain, handed to the
// studio server over its stdin pipe as one JSON line each, never written to
// disk, a log, an argument or the environment (docs/studio/CONTRACT.md,
// sections 16 and 22.9; docs/studio/ASSISTANT.md, section 6).
//
//   {"caterva_control":"assistant_key","provider":"anthropic","key":"..."}
//   {"caterva_control":"assistant_key_clear","provider":"anthropic"}
//
// A key value never appears in a log line, an error string or a reply.

import Foundation
import Security

/// The Keychain behind a seam, so a test can use a fake.
protocol KeyStoring {
    func set(provider: String, key: String) -> Bool
    func read(provider: String) -> String?
    func clear(provider: String) -> Bool
    func isPresent(provider: String) -> Bool
}

enum AssistantKeychain {
    static let service = "org.caterva.assistant"
    /// "local" takes no key, so it is not here.
    static let providers = ["anthropic", "openai", "groq", "openrouter", "mistral"]

    static func validProvider(_ provider: String) -> Bool { providers.contains(provider) }

    /// 8...512 characters, no whitespace, no control characters.
    static func validKey(_ key: String) -> Bool {
        guard (8...512).contains(key.count) else { return false }
        return !key.unicodeScalars.contains {
            CharacterSet.whitespacesAndNewlines.contains($0) || CharacterSet.controlCharacters.contains($0)
        }
    }

    static func controlLine(set provider: String, key: String) -> Data? {
        guard validProvider(provider), validKey(key) else { return nil }
        return line(["caterva_control": "assistant_key", "provider": provider, "key": key])
    }

    static func controlLine(clear provider: String) -> Data? {
        guard validProvider(provider) else { return nil }
        return line(["caterva_control": "assistant_key_clear", "provider": provider])
    }

    private static func line(_ object: [String: String]) -> Data? {
        guard var data = try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]) else { return nil }
        data.append(0x0A)
        return data
    }
}

/// The login Keychain (not the data-protection one), one generic password per
/// provider, readable only while the Mac is unlocked and never synced.
struct SecurityKeychain: KeyStoring {
    private func query(_ provider: String) -> [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: AssistantKeychain.service,
         kSecAttrAccount as String: provider]
    }

    func set(provider: String, key: String) -> Bool {
        guard AssistantKeychain.validProvider(provider), AssistantKeychain.validKey(key) else { return false }
        let data = Data(key.utf8)
        let update = SecItemUpdate(query(provider) as CFDictionary,
                                   [kSecValueData as String: data] as CFDictionary)
        if update == errSecSuccess { return true }
        guard update == errSecItemNotFound else { return false }
        var add = query(provider)
        add[kSecValueData as String] = data
        add[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        return SecItemAdd(add as CFDictionary, nil) == errSecSuccess
    }

    func read(provider: String) -> String? {
        guard AssistantKeychain.validProvider(provider) else { return nil }
        var q = query(provider)
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    func clear(provider: String) -> Bool {
        guard AssistantKeychain.validProvider(provider) else { return false }
        let status = SecItemDelete(query(provider) as CFDictionary)
        return status == errSecSuccess || status == errSecItemNotFound
    }

    func isPresent(provider: String) -> Bool {
        guard AssistantKeychain.validProvider(provider) else { return false }
        var q = query(provider)
        q[kSecReturnAttributes as String] = true   // attributes only: the value is not read
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        return SecItemCopyMatching(q as CFDictionary, nil) == errSecSuccess
    }
}

/// Writes control lines to the server. `write` is wired by the shell to the
/// server's stdin pipe and must ignore a closed pipe.
final class AssistantKeyRelay {
    let store: KeyStoring
    private let write: (Data) -> Void

    init(store: KeyStoring = SecurityKeychain(), write: @escaping (Data) -> Void) {
        self.store = store
        self.write = write
    }

    /// Every stored key, one line each. Called once the server has printed its URL.
    func sendAll() {
        for provider in AssistantKeychain.providers { send(provider: provider) }
    }

    func send(provider: String) {
        guard let key = store.read(provider: provider),
              let line = AssistantKeychain.controlLine(set: provider, key: key) else { return }
        write(line)
    }

    func clear(provider: String) {
        if let line = AssistantKeychain.controlLine(clear: provider) { write(line) }
    }

    /// Safe write to a pipe's handle: an error such as EPIPE is ignored
    /// (FileHandle.write(_:) would raise an Objective-C exception instead).
    static func write(_ data: Data, to handle: FileHandle?) {
        guard let handle else { return }
        try? handle.write(contentsOf: data)
    }
}

/// What the web bridge talks to.
final class AssistantKeyBridge {
    private let store: KeyStoring
    private let relay: AssistantKeyRelay

    init(store: KeyStoring, relay: AssistantKeyRelay) {
        self.store = store
        self.relay = relay
    }

    /// nil on success, else a message that never contains the key.
    func set(provider: String, key: String) -> String? {
        guard AssistantKeychain.validProvider(provider), AssistantKeychain.validKey(key) else {
            return "that is not a usable key"
        }
        guard store.set(provider: provider, key: key) else { return "could not store the key" }
        relay.send(provider: provider)
        return nil
    }

    func clear(provider: String) -> String? {
        guard AssistantKeychain.validProvider(provider) else { return "unknown provider" }
        guard store.clear(provider: provider) else { return "could not remove the key" }
        relay.clear(provider: provider)
        return nil
    }

    /// Exactly "present" or "absent".
    func status(provider: String) -> String {
        AssistantKeychain.validProvider(provider) && store.isPresent(provider: provider) ? "present" : "absent"
    }
}
