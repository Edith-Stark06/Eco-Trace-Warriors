import 'package:flutter/material.dart';

import '../../education/screens/education_screen.dart';
import '../../profile/screens/profile_screen.dart';
import '../../rewards/screens/rewards_screen.dart';
import '../../scan/screens/scan_screen.dart';
import '../../submissions/screens/report_waste_screen.dart';
import '../../submissions/screens/submission_history_screen.dart';

/// Tabbed shell: Reports / Rewards / Learn / Profile, with a floating
/// "Report" action and a Scan shortcut in the app bar. Consolidates what the
/// design brief lists as separate Home/Scan-Device screens into one
/// coherent navigation shell — the same rationale as the Collector app's
/// Home/Task-List consolidation (`reports/P6_3_MOBILE_COLLECTOR.md` §4).
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _tabIndex = 0;

  @override
  Widget build(BuildContext context) {
    const screens = [
      SubmissionHistoryScreen(embedded: true),
      RewardsScreen(embedded: true),
      EducationScreen(embedded: true),
      ProfileScreen(embedded: true),
    ];
    const titles = ['My Reports', 'Rewards', 'Learn', 'Profile'];

    return Scaffold(
      appBar: AppBar(
        title: Text(titles[_tabIndex]),
        actions: [
          IconButton(
            icon: const Icon(Icons.qr_code_scanner),
            tooltip: 'Scan code',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const ScanScreen()),
            ),
          ),
        ],
      ),
      body: screens[_tabIndex],
      floatingActionButton: _tabIndex == 0
          ? FloatingActionButton.extended(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const ReportWasteScreen()),
              ),
              icon: const Icon(Icons.add),
              label: const Text('Report'),
            )
          : null,
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tabIndex,
        onDestinationSelected: (index) => setState(() => _tabIndex = index),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.inventory_2_outlined), label: 'Reports'),
          NavigationDestination(icon: Icon(Icons.card_giftcard_outlined), label: 'Rewards'),
          NavigationDestination(icon: Icon(Icons.menu_book_outlined), label: 'Learn'),
          NavigationDestination(icon: Icon(Icons.person_outline), label: 'Profile'),
        ],
      ),
    );
  }
}
