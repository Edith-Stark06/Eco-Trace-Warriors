import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/utils/result.dart';
import '../../../shared/widgets/empty_state.dart';
import '../../../shared/widgets/error_state.dart';
import '../../../shared/widgets/loading_indicator.dart';
import '../models/reward.dart';
import '../providers/rewards_providers.dart';

/// Reward balance + history — `GET /rewards/balance`, `GET /rewards/history`.
///
/// Read-only: there is no consumer-facing redemption endpoint on the
/// backend (`POST /rewards/issue/:submissionId` is an ADMIN-only manual
/// override; rewards are issued automatically when a recycler completes
/// processing — `reward.routes.ts`). A "Redeem" button here would have
/// nowhere real to submit to, so this screen shows balance/history/impact
/// only. See `reports/P6_4_MOBILE_CONSUMER.md`.
class RewardsScreen extends ConsumerWidget {
  const RewardsScreen({super.key, this.embedded = false});

  final bool embedded;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final balance = ref.watch(rewardBalanceProvider);
    final history = ref.watch(rewardHistoryProvider);

    final body = RefreshIndicator(
      onRefresh: () async {
        ref.invalidate(rewardBalanceProvider);
        ref.invalidate(rewardHistoryProvider);
      },
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          balance.when(
            loading: () => const LoadingIndicator(),
            error: (error, _) => ErrorState(
              failure: error is AppFailure ? error : AppFailure.unknown('$error'),
              onRetry: () => ref.invalidate(rewardBalanceProvider),
            ),
            data: (b) => _BalanceCard(balance: b),
          ),
          const SizedBox(height: 24),
          Text('History', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          history.when(
            loading: () => const LoadingIndicator(),
            error: (error, _) => ErrorState(
              failure: error is AppFailure ? error : AppFailure.unknown('$error'),
              onRetry: () => ref.invalidate(rewardHistoryProvider),
            ),
            data: (items) {
              if (items.isEmpty) {
                return const EmptyState(
                  icon: Icons.card_giftcard_outlined,
                  title: 'No rewards yet',
                  subtitle: 'Green Coins are awarded automatically once a reported '
                      'item is recycled.',
                );
              }
              return Column(
                children: items.map((t) => _RewardTile(transaction: t)).toList(),
              );
            },
          ),
        ],
      ),
    );

    if (embedded) return body;
    return Scaffold(appBar: AppBar(title: const Text('Rewards')), body: body);
  }
}

class _BalanceCard extends StatelessWidget {
  const _BalanceCard({required this.balance});

  final RewardBalance balance;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      color: AppTheme.primaryGreen,
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Green Coins',
              style: theme.textTheme.labelLarge?.copyWith(color: Colors.white70),
            ),
            Text(
              '${balance.greenCoins}',
              style: theme.textTheme.displaySmall?.copyWith(color: Colors.white),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                _ImpactStat(label: 'Rewards', value: '${balance.totalRewards}'),
                _ImpactStat(
                  label: 'CO2 saved',
                  value: '${balance.totalCO2Saved.toStringAsFixed(1)} kg',
                ),
                _ImpactStat(
                  label: 'Landfill diverted',
                  value: '${balance.totalLandfillDiverted.toStringAsFixed(1)} kg',
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _ImpactStat extends StatelessWidget {
  const _ImpactStat({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(value, style: theme.textTheme.titleMedium?.copyWith(color: Colors.white)),
          Text(label, style: theme.textTheme.bodySmall?.copyWith(color: Colors.white70)),
        ],
      ),
    );
  }
}

class _RewardTile extends StatelessWidget {
  const _RewardTile({required this.transaction});

  final RewardTransaction transaction;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        leading: const Icon(Icons.eco_outlined),
        title: Text(transaction.submissionCategory),
        subtitle: Text(DateFormat.yMMMd().format(transaction.createdAt.toLocal())),
        trailing: Text('+${transaction.points}', style: Theme.of(context).textTheme.titleMedium),
      ),
    );
  }
}
