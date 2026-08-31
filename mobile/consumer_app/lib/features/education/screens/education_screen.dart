import 'package:flutter/material.dart';

/// Static recycling-education content. Genuinely real (not a backend-backed
/// placeholder) — there is no content-management backend for this, and none
/// is needed for informational copy that isn't user- or account-specific.
class EducationScreen extends StatelessWidget {
  const EducationScreen({super.key, this.embedded = false});

  final bool embedded;

  static const _topics = [
    (
      Icons.battery_alert_outlined,
      'Batteries need special handling',
      'Lithium-ion batteries can catch fire if crushed or punctured. Never '
          'put them in regular trash — report them for pickup instead.',
    ),
    (
      Icons.dangerous_outlined,
      'E-waste contains hazardous materials',
      'Lead, mercury, and cadmium in old electronics can contaminate soil '
          'and water if sent to a landfill. Recycling recovers these safely.',
    ),
    (
      Icons.recycling_outlined,
      'Most of a device can be recovered',
      'Metals, plastics, and glass in e-waste are recoverable and reusable '
          'in new products, reducing the need for raw material extraction.',
    ),
    (
      Icons.co2_outlined,
      'Recycling avoids carbon emissions',
      'Manufacturing new electronics from raw materials is far more carbon '
          'intensive than recovering materials from recycled devices.',
    ),
    (
      Icons.data_object_outlined,
      'Wipe your data first',
      'Factory-reset any device with storage before handing it over for '
          'pickup, even though EcoTrace does not process device data itself.',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    final body = ListView.separated(
      padding: const EdgeInsets.all(16),
      itemCount: _topics.length,
      separatorBuilder: (_, __) => const SizedBox(height: 8),
      itemBuilder: (context, index) {
        final (icon, title, body) = _topics[index];
        return Card(
          child: ListTile(
            leading: Icon(icon),
            title: Text(title),
            subtitle: Text(body),
            isThreeLine: true,
          ),
        );
      },
    );

    if (embedded) return body;
    return Scaffold(appBar: AppBar(title: const Text('Recycling Education')), body: body);
  }
}
