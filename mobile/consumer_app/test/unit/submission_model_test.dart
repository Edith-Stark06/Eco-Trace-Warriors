import 'package:ecotrace_consumer/features/submissions/models/submission.dart';
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

  group('Submission.fromJson / isEditable', () {
    Map<String, dynamic> baseJson({String status = 'PENDING'}) => {
          'id': 'sub-1',
          'userId': 'user-1',
          'category': 'Laptop',
          'description': 'Old laptop, screen cracked',
          'estimatedWeight': 2.5,
          'address': '123 Example St',
          'latitude': 12.34,
          'longitude': 56.78,
          'imageUrls': <String>[],
          'status': status,
          'recoveredWeight': null,
          'co2Saved': null,
          'rewardIssued': false,
          'createdAt': '2026-01-01T00:00:00.000Z',
          'updatedAt': '2026-01-02T00:00:00.000Z',
        };

    test('parses every field correctly', () {
      final submission = Submission.fromJson(baseJson());
      expect(submission.id, 'sub-1');
      expect(submission.category, 'Laptop');
      expect(submission.estimatedWeight, 2.5);
      expect(submission.status, SubmissionStatus.pending);
      expect(submission.rewardIssued, isFalse);
    });

    test('isEditable is true only while PENDING', () {
      expect(Submission.fromJson(baseJson(status: 'PENDING')).isEditable, isTrue);
      for (final status in [
        'ASSIGNED',
        'ACCEPTED',
        'IN_PROGRESS',
        'COLLECTED',
        'RECYCLING',
        'RECYCLED',
        'COMPLETED',
        'REJECTED',
      ]) {
        expect(
          Submission.fromJson(baseJson(status: status)).isEditable,
          isFalse,
          reason: '$status should not be editable',
        );
      }
    });

    test('parses recoveredWeight and co2Saved when present', () {
      final json = baseJson(status: 'RECYCLED')
        ..['recoveredWeight'] = 2.1
        ..['co2Saved'] = 5.4;
      final submission = Submission.fromJson(json);
      expect(submission.recoveredWeight, 2.1);
      expect(submission.co2Saved, 5.4);
    });
  });
}
