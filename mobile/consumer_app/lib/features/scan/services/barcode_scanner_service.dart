import 'dart:async';

import 'package:mobile_scanner/mobile_scanner.dart';

/// Thin abstraction over QR/barcode scanning — same rationale as the
/// Collector app's identical service
/// (`mobile/collector_app/lib/features/capture/services/barcode_scanner_service.dart`):
/// screens depend on this interface, not directly on `mobile_scanner`.
abstract class BarcodeScannerService {
  Future<String?> scan();
}

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
