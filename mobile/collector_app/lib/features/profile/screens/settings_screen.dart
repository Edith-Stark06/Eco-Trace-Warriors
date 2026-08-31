import 'package:flutter/material.dart';

import '../../../core/config/app_config.dart';

/// App diagnostics / configuration reference. Deliberately read-only — the
/// API endpoint is a compile-time `--dart-define`, not something meant to be
/// changed at runtime by a collector in the field.
class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        children: [
          const ListTile(
            leading: Icon(Icons.dns_outlined),
            title: Text('API endpoint'),
            subtitle: Text(AppConfig.apiBaseUrl),
          ),
          const ListTile(
            leading: Icon(Icons.info_outline),
            title: Text('App version'),
            subtitle: Text('1.0.0 (P6.3)'),
          ),
          const AboutListTile(
            icon: Icon(Icons.eco_outlined),
            applicationName: 'EcoTrace Collector',
            applicationVersion: '1.0.0',
            aboutBoxChildren: [
              Padding(
                padding: EdgeInsets.only(top: 8),
                child: Text(
                  'EcoTrace India — collector app for managing e-waste pickup assignments.',
                ),
              ),
            ],
            child: Text('About EcoTrace Collector'),
          ),
        ],
      ),
    );
  }
}
