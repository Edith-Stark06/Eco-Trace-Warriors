import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../auth/providers/auth_providers.dart';
import '../../auth/screens/login_screen.dart';
import 'settings_screen.dart';

class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key, this.embedded = false});

  final bool embedded;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profile = ref.watch(authControllerProvider).profile;
    final theme = Theme.of(context);

    final body = ListView(
      padding: const EdgeInsets.all(24),
      children: [
        CircleAvatar(
          radius: 40,
          child: Text(
            profile != null && profile.fullName.isNotEmpty
                ? profile.fullName.trim()[0].toUpperCase()
                : '?',
            style: theme.textTheme.headlineMedium,
          ),
        ),
        const SizedBox(height: 16),
        Center(
          child: Text(profile?.fullName ?? '—', style: theme.textTheme.titleLarge),
        ),
        Center(
          child: Text(
            profile?.email ?? '',
            style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.outline),
          ),
        ),
        const SizedBox(height: 8),
        Center(child: Chip(label: Text(profile?.role ?? 'COLLECTOR'))),
        const SizedBox(height: 32),
        if (profile?.phone != null)
          ListTile(
            leading: const Icon(Icons.phone_outlined),
            title: const Text('Phone'),
            subtitle: Text(profile!.phone!),
          ),
        if (profile?.region != null)
          ListTile(
            leading: const Icon(Icons.map_outlined),
            title: const Text('Region'),
            subtitle: Text(profile!.region!),
          ),
        ListTile(
          leading: const Icon(Icons.settings_outlined),
          title: const Text('Settings'),
          trailing: const Icon(Icons.chevron_right),
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => const SettingsScreen()),
          ),
        ),
        const SizedBox(height: 24),
        OutlinedButton.icon(
          onPressed: () async {
            await ref.read(authControllerProvider.notifier).logout();
            if (!context.mounted) return;
            Navigator.of(context).pushAndRemoveUntil(
              MaterialPageRoute(builder: (_) => const LoginScreen()),
              (route) => false,
            );
          },
          icon: const Icon(Icons.logout),
          label: const Text('Log out'),
        ),
      ],
    );

    if (embedded) return body;
    return Scaffold(appBar: AppBar(title: const Text('Profile')), body: body);
  }
}
