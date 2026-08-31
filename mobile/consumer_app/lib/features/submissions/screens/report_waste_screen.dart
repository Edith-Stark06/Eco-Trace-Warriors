import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/submissions_providers.dart';

/// The consumer's "report e-waste for pickup" flow — `POST /submissions`.
/// This is what the mobile design brief called "device capture"; the real
/// backend models it as a pickup request (category/weight/address/geo), not
/// an AI-detected device — see `reports/P6_4_MOBILE_CONSUMER.md`.
class ReportWasteScreen extends ConsumerStatefulWidget {
  const ReportWasteScreen({super.key});

  @override
  ConsumerState<ReportWasteScreen> createState() => _ReportWasteScreenState();
}

class _ReportWasteScreenState extends ConsumerState<ReportWasteScreen> {
  final _formKey = GlobalKey<FormState>();
  final _categoryController = TextEditingController();
  final _descriptionController = TextEditingController();
  final _weightController = TextEditingController();
  final _addressController = TextEditingController();
  final _latitudeController = TextEditingController();
  final _longitudeController = TextEditingController();

  @override
  void dispose() {
    _categoryController.dispose();
    _descriptionController.dispose();
    _weightController.dispose();
    _addressController.dispose();
    _latitudeController.dispose();
    _longitudeController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    final ok = await ref.read(createSubmissionControllerProvider.notifier).submit(
          category: _categoryController.text.trim(),
          description: _descriptionController.text.trim(),
          estimatedWeight: double.parse(_weightController.text.trim()),
          address: _addressController.text.trim(),
          latitude: double.parse(_latitudeController.text.trim()),
          longitude: double.parse(_longitudeController.text.trim()),
        );
    if (!mounted) return;
    if (ok) {
      Navigator.of(context).pop();
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Pickup request submitted.')),
      );
    }
  }

  String? _requiredValidator(String? value, {String label = 'This field'}) {
    if (value == null || value.trim().isEmpty) return '$label is required';
    return null;
  }

  String? _numberValidator(String? value, {bool positive = true}) {
    if (value == null || value.trim().isEmpty) return 'Required';
    final parsed = double.tryParse(value.trim());
    if (parsed == null) return 'Enter a valid number';
    if (positive && parsed <= 0) return 'Must be greater than 0';
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(createSubmissionControllerProvider);

    ref.listen(createSubmissionControllerProvider, (previous, next) {
      next.whenOrNull(
        error: (error, _) => ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('$error')),
        ),
      );
    });

    return Scaffold(
      appBar: AppBar(title: const Text('Report E-Waste')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextFormField(
                controller: _categoryController,
                decoration: const InputDecoration(labelText: 'Category (e.g. "Laptop", "E-waste")'),
                validator: (v) => _requiredValidator(v, label: 'Category'),
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: _descriptionController,
                maxLines: 3,
                decoration: const InputDecoration(labelText: 'Description (optional)'),
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: _weightController,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: 'Estimated weight (kg)'),
                validator: _numberValidator,
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: _addressController,
                decoration: const InputDecoration(labelText: 'Pickup address'),
                validator: (v) => _requiredValidator(v, label: 'Address'),
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _latitudeController,
                      keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
                      decoration: const InputDecoration(labelText: 'Latitude'),
                      validator: (v) {
                        final err = _numberValidator(v, positive: false);
                        if (err != null) return err;
                        final n = double.parse(v!.trim());
                        return (n < -90 || n > 90) ? 'Must be between -90 and 90' : null;
                      },
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: TextFormField(
                      controller: _longitudeController,
                      keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
                      decoration: const InputDecoration(labelText: 'Longitude'),
                      validator: (v) {
                        final err = _numberValidator(v, positive: false);
                        if (err != null) return err;
                        final n = double.parse(v!.trim());
                        return (n < -180 || n > 180) ? 'Must be between -180 and 180' : null;
                      },
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                'Coordinates identify the pickup location for your collector. '
                'A future release can fill these in automatically from device location.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: 24),
              ElevatedButton(
                onPressed: state.isLoading ? null : _submit,
                child: state.isLoading
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Submit pickup request'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
