import 'dart:async';

import 'package:mobile_scanner/mobile_scanner.dart';

/// Thin abstraction over QR/barcode scanning.
///
/// Kept as its own service — same rationale as `CameraService` — so a
/// screen depends on this interface, not directly on `mobile_scanner`.
///
/// Not currently wired to a lookup flow: the backend has no
/// "resolve submission by scanned code" endpoint — a collector locates a
/// pickup by browsing `GET /collector/submissions`
/// (`features/tasks/screens` in this app), not by scanning a code. This
/// abstraction is provided as a required capability and is ready to back a
/// future "scan to open" shortcut once/if the backend exposes a
/// code-to-submission lookup.
abstract class BarcodeScannerService {
  /// Returns the decoded string of the first barcode/QR code scanned, or
  /// `null` if the collector cancels before anything is detected.
  Future<String?> scan();
}

/// Real implementation backed by `mobile_scanner`. Callers are expected to
/// host the returned [MobileScannerController] inside a `MobileScannerView`
/// (or equivalent) widget — this service owns detection-stream plumbing
/// only, not the camera preview UI, so it can be unit-tested without one.
class MobileBarcodeScannerService implements BarcodeScannerService {
  MobileBarcodeScannerService({MobileScannerController? controller})
      : _controller = controller ?? MobileScannerController();

  final MobileScannerController _controller;

  MobileScannerController get controller => _controller;

  @override
  Future<String?> scan() async {
    final completer = Completer<String?>();
    late final StreamSubscription<BarcodeCapture> subscription;
    subscription = _controller.barcodes.listen((capture) {
      final value = capture.barcodes.isNotEmpty ? capture.barcodes.first.rawValue : null;
      if (value != null && !completer.isCompleted) {
        completer.complete(value);
      }
    });
    final result = await completer.future;
    await subscription.cancel();
    return result;
  }

  void dispose() {
    _controller.dispose();
  }
}
