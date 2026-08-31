import 'package:image_picker/image_picker.dart';

/// Thin abstraction over device camera/gallery capture.
///
/// Kept as its own service (rather than calling `image_picker` directly from
/// screens) so: (1) screens stay testable against a fake implementation with
/// no camera hardware, and (2) if the capture backend ever changes (a
/// different plugin, a custom camera UI), only this file changes.
///
/// Not currently wired to any upload flow: the backend's collector-workflow
/// endpoints (`accept`/`start`/`complete` in
/// `backend/src/modules/submission/submission.routes.ts`) take no photo
/// payload, and general `imageUrls` updates are only permitted for a
/// submission's owning consumer while it is still `PENDING`
/// (`submission.service.ts` — `update()`). A "photo of the pickup, for my
/// own reference" capability using this service is a natural next step once
/// a backend endpoint exists to receive it — see
/// `reports/P6_3_MOBILE_COLLECTOR.md` §Limitations.
abstract class CameraService {
  /// Captures a single photo from the device camera. Returns `null` if the
  /// collector cancels.
  Future<CapturedImage?> capturePhoto();

  /// Picks a single photo from the device gallery. Returns `null` if the
  /// collector cancels.
  Future<CapturedImage?> pickFromGallery();
}

class CapturedImage {
  const CapturedImage({required this.path, required this.capturedAt});

  final String path;
  final DateTime capturedAt;
}

/// Real implementation backed by `image_picker`.
class ImagePickerCameraService implements CameraService {
  ImagePickerCameraService({ImagePicker? picker}) : _picker = picker ?? ImagePicker();

  final ImagePicker _picker;

  @override
  Future<CapturedImage?> capturePhoto() async {
    final file = await _picker.pickImage(source: ImageSource.camera, imageQuality: 85);
    if (file == null) return null;
    return CapturedImage(path: file.path, capturedAt: DateTime.now());
  }

  @override
  Future<CapturedImage?> pickFromGallery() async {
    final file = await _picker.pickImage(source: ImageSource.gallery, imageQuality: 85);
    if (file == null) return null;
    return CapturedImage(path: file.path, capturedAt: DateTime.now());
  }
}
