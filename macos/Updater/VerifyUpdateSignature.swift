// Checks an update archive's EdDSA signature against a public key, with
// CryptoKit and nothing of Sparkle's: the release workflow runs it on the
// archive it just signed, with the public key committed in macos/Info.plist
// (SUPublicEDKey), so a repository secret that does not match that key fails
// the release instead of shipping updates that every installed app rejects.
//
//   verify-update-signature <public key, base64> <signature, base64> <file>
//
// Exit 0 and "VALID" when the signature is good, 1 and "INVALID" when it is
// not, 2 on a malformed argument.

import CryptoKit
import Foundation

let arguments = CommandLine.arguments
guard arguments.count == 4,
      let keyBytes = Data(base64Encoded: arguments[1]), keyBytes.count == 32,
      let signature = Data(base64Encoded: arguments[2]), signature.count == 64,
      let message = FileManager.default.contents(atPath: arguments[3]),
      let key = try? Curve25519.Signing.PublicKey(rawRepresentation: keyBytes) else {
    print("usage: verify-update-signature <public key, base64, 32 bytes> <signature, base64, 64 bytes> <file>")
    exit(2)
}
if key.isValidSignature(signature, for: message) {
    print("VALID")
    exit(0)
}
print("INVALID")
exit(1)
