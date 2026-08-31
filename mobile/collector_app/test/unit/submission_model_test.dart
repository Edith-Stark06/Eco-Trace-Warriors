import 'package:ecotrace_collector/features/tasks/models/submission.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('SubmissionStatus.fromWire', () {
    test('parses every backend status value', () {
      const wireValues = {
        'PENDING': SubmissionStatus.pending,
        'ASSIGNED': SubmissionStatus.assigned,
        'ACCEPTED': SubmissionStatus.accepted,
        'IN_PROGRESS': SubmissionStatus.inProgress,
        'COLLECTED': SubmissionStatus.collected,
        'RECYCLING': SubmissionStatus.recycling,
        'RECYCLED': SubmissionStatus.recycled,
        'COMPLETED': SubmissionStatus.completed,
        'REJECTED': SubmissionStatus.rejected,
      };
      for (final entry in wireValues.entries) {
        expect(SubmissionStatus.fromWire(entry.key), entry.value);
      }
    });

    test('throws on an unrecognized status', () {
      expect(() => SubmissionStatus.fromWire('BOGUS'), throwsArgumentError);
    });
  });

  group('Submission.fromJson', () {
    Map<String, dynamic> baseJson({String status = 'ASSIGNED'}) => {
          'id': 'sub-1',
          'userId': 'user-1',
          'category': 'e-waste',
          'description': 'Old laptop and charger',
          'estimatedWeight': 3.5,
          'address': '123 Example St',
          'latitude': 12.34,
          'longitude': 56.78,
          'imageUrls': <String>['https://example.com/a.jpg'],
          'status': status,
          'assignedCollectorId': 'collector-1',
          'pickupScheduledAt': null,
          'completedAt': null,
          'createdAt': '2026-01-01T00:00:00.000Z',
          'updatedAt': '2026-01-02T00:00:00.000Z',
        };

    test('parses every field correctly', () {
      final submission = Submission.fromJson(baseJson());
      expect(submission.id, 'sub-1');
      expect(submission.category, 'e-waste');
      expect(submission.estimatedWeight, 3.5);
      expect(submission.status, SubmissionStatus.assigned);
      expect(submission.imageUrls, ['https://example.com/a.jpg']);
      expect(submission.pickupScheduledAt, isNull);
      expect(submission.createdAt, DateTime.parse('2026-01-01T00:00:00.000Z'));
    });

    test('defaults imageUrls to an empty list when absent', () {
      final json = baseJson()..remove('imageUrls');
      final submission = Submission.fromJson(json);
      expect(submission.imageUrls, isEmpty);
    });

    test('nextAction maps ASSIGNED -> accept, ACCEPTED -> start, IN_PROGRESS -> complete', () {
      expect(Submission.fromJson(baseJson(status: 'ASSIGNED')).nextAction, SubmissionAction.accept);
      expect(Submission.fromJson(baseJson(status: 'ACCEPTED')).nextAction, SubmissionAction.start);
      expect(
        Submission.fromJson(baseJson(status: 'IN_PROGRESS')).nextAction,
        SubmissionAction.complete,
      );
    });

    test('nextAction is null for statuses a collector cannot act on', () {
      for (final status in ['PENDING', 'COLLECTED', 'RECYCLING', 'RECYCLED', 'COMPLETED', 'REJECTED']) {
        expect(
          Submission.fromJson(baseJson(status: status)).nextAction,
          isNull,
          reason: '$status should have no collector action',
        );
      }
    });
  });
}
