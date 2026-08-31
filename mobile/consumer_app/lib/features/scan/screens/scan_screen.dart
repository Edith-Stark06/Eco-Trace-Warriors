import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../submissions/screens/submission_detail_screen.dart';

/// Scans a QR code and, if it looks like a submission id (a UUID — the
/// shape `PublicSubmission.id` always takes,
/// `backend/prisma/schema.prisma`'s `@default(uuid())`), opens that
/// report's detail screen. There is no backend endpoint to resolve an
/// arbitrary scanned code against a device passport (see
/// `DeviceVerificationScreen`), so this is the honest, real capability the
/// current backend actually supports: a shortcut into a report you already
/// have permission to view, not a device-identity lookup.
class ScanScreen extends StatefulWidget {
  const ScanScreen({super.key});

  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> {
  final _controller = MobileScannerController();
  bool _handled = false;

  static final _uuidPattern = RegExp(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$',
  );

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _onDetect(BarcodeCapture capture) {
    if (_handled) return;
    final value = capture.barcodes.isNotEmpty ? capture.barcodes.first.rawValue : null;
    if (value == null) return;

    if (_uuidPattern.hasMatch(value)) {
      _handled = true;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => SubmissionDetailScreen(submissionId: value)),
      );
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('This code does not match a known EcoTrace report.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Scan Code')),
      body: MobileScanner(controller: _controller, onDetect: _onDetect),
    );
  }
}
