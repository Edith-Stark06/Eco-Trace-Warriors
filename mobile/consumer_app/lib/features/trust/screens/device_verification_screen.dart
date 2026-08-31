import 'package:flutter/material.dart';

/// Device Passport / Blockchain Trust Verification.
///
/// Honestly unavailable, not faked: `backend/`'s own infrastructure layer
/// defines `FabricClient`/`AiClient` as explicit placeholders —
/// `backend/src/infrastructure/fabric/fabric.client.ts`'s
/// `createFabricClient()` literally rejects every call with "Fabric client
/// is not available until Phase 7 (Blockchain)", and neither client is
/// imported by any module or route (verified: zero call sites). Separately,
/// P6.1/P6.2 built a *working* Fabric chaincode + Gateway client — but in
/// the Python `intelligence/device_ai` service, which this Node `backend/`
/// (what the mobile apps talk to) does not yet call into.
///
/// Building a screen that pretends to verify a device passport against the
/// chain right now would be exactly the "fake production behavior" the
/// work order prohibits. This screen states the real status instead, with a
/// repository seam (`TrustRepository`) ready to wire up once `backend/`
/// exposes a real endpoint — see `reports/P6_4_MOBILE_CONSUMER.md`.
class DeviceVerificationScreen extends StatelessWidget {
  const DeviceVerificationScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Device Verification')),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.verified_outlined, size: 64, color: theme.colorScheme.outline),
              const SizedBox(height: 16),
              Text(
                'Blockchain verification is not yet connected',
                style: theme.textTheme.titleMedium,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 12),
              Text(
                'EcoTrace\'s Fabric chaincode and Gateway client are built, but '
                'the backend this app talks to has not yet been wired to them '
                '(the backend\'s own code marks this "Phase 7 — Blockchain", not '
                'yet started). This screen will show real, on-chain verification '
                'once that connection exists.',
                style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.outline),
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
