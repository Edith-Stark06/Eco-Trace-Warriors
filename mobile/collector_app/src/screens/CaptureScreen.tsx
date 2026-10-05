import React, { useRef, useState } from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { ErrorState } from '../components/ErrorState';
import { theme } from '../theme';

type Props = NativeStackScreenProps<RootStackParamList, 'Capture'>;

interface Shot {
  uri: string;
  name: string;
  type: string;
}

/**
 * Camera capture with preview + retake, mirrors camera_service.dart. Up to
 * 5 images (matching the device_ai MAX_IMAGES convention) are collected
 * before moving on to registration.
 */
export function CaptureScreen({ navigation, route }: Props) {
  const submissionId = route.params?.submissionId;
  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<CameraView>(null);
  const [shots, setShots] = useState<Shot[]>([]);
  const [previewUri, setPreviewUri] = useState<string | null>(null);

  if (!permission) {
    return <View style={styles.container} />;
  }

  if (!permission.granted) {
    return (
      <ErrorState
        message={
          permission.canAskAgain
            ? 'Camera access is required to capture device photos.'
            : 'Camera access was denied. Enable it in system settings to continue.'
        }
        onRetry={permission.canAskAgain ? requestPermission : undefined}
      />
    );
  }

  const handleCapture = async () => {
    const photo = await cameraRef.current?.takePictureAsync({ quality: 0.8 });
    if (photo?.uri) {
      setPreviewUri(photo.uri);
    }
  };

  const handleKeep = () => {
    if (!previewUri) return;
    setShots((prev) => [
      ...prev,
      { uri: previewUri, name: `capture-${Date.now()}.jpg`, type: 'image/jpeg' },
    ]);
    setPreviewUri(null);
  };

  const handleRetake = () => setPreviewUri(null);

  const handleContinue = () => {
    if (shots.length === 0) return;
    navigation.navigate('RegisterDevice', { images: shots, submissionId });
  };

  if (previewUri) {
    return (
      <View style={styles.container}>
        <Image source={{ uri: previewUri }} style={styles.preview} accessibilityLabel="Captured photo preview" />
        <View style={styles.previewActions}>
          <Pressable style={styles.secondaryButton} onPress={handleRetake} accessibilityRole="button" accessibilityLabel="Retake photo">
            <Text style={styles.secondaryButtonText}>Retake</Text>
          </Pressable>
          <Pressable style={styles.primaryButton} onPress={handleKeep} accessibilityRole="button" accessibilityLabel="Keep photo">
            <Text style={styles.primaryButtonText}>Keep photo</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <CameraView ref={cameraRef} style={styles.camera} facing="back" />

      {/* Modern HUD Framing Overlays */}
      <View style={styles.reticleOverlay} pointerEvents="none">
        <View style={styles.reticleBox}>
          <View style={[styles.corner, styles.cornerTL]} />
          <View style={[styles.corner, styles.cornerTR]} />
          <View style={[styles.corner, styles.cornerBL]} />
          <View style={[styles.corner, styles.cornerBR]} />
        </View>
        <Text style={styles.reticleHint}>Center device in frame for AI detection</Text>
      </View>

      <View style={styles.footer}>
        <View style={styles.countBadge}>
          <Text style={styles.count} accessibilityLiveRegion="polite">
            {shots.length} photo(s) captured
          </Text>
        </View>

        <View style={styles.footerActions}>
          <View style={styles.sideSpacer} />

          {/* Centered Shutter Button */}
          <Pressable
            style={styles.shutterOuter}
            onPress={handleCapture}
            accessibilityRole="button"
            accessibilityLabel="Take photo"
            testID="capture-shutter-button"
          >
            <View style={styles.captureButton} />
          </Pressable>

          {/* Continue CTA */}
          <View style={styles.sideAction}>
            <Pressable
              style={[styles.continueButton, shots.length === 0 && styles.disabled]}
              onPress={handleContinue}
              disabled={shots.length === 0}
              accessibilityRole="button"
              accessibilityLabel="Continue to device registration"
              accessibilityState={{ disabled: shots.length === 0 }}
            >
              <Text style={styles.continueButtonText}>Done ({shots.length})</Text>
            </Pressable>
          </View>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000000' },
  camera: { flex: 1 },
  preview: { flex: 1 },
  previewActions: {
    flexDirection: 'row',
    gap: 12,
    padding: theme.spacing.lg,
    backgroundColor: 'rgba(15, 23, 42, 0.95)',
  },
  reticleOverlay: {
    position: 'absolute',
    top: 60,
    left: 0,
    right: 0,
    bottom: 160,
    alignItems: 'center',
    justifyContent: 'center',
  },
  reticleBox: {
    width: 260,
    height: 260,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.2)',
    borderRadius: theme.radius.lg,
    position: 'relative',
  },
  corner: {
    position: 'absolute',
    width: 28,
    height: 28,
    borderColor: theme.colors.forest[400],
  },
  cornerTL: {
    top: -2,
    left: -2,
    borderTopWidth: 4,
    borderLeftWidth: 4,
    borderTopLeftRadius: theme.radius.md,
  },
  cornerTR: {
    top: -2,
    right: -2,
    borderTopWidth: 4,
    borderRightWidth: 4,
    borderTopRightRadius: theme.radius.md,
  },
  cornerBL: {
    bottom: -2,
    left: -2,
    borderBottomWidth: 4,
    borderLeftWidth: 4,
    borderBottomLeftRadius: theme.radius.md,
  },
  cornerBR: {
    bottom: -2,
    right: -2,
    borderBottomWidth: 4,
    borderRightWidth: 4,
    borderBottomRightRadius: theme.radius.md,
  },
  reticleHint: {
    color: '#FFFFFF',
    fontSize: theme.typography.size.xs,
    fontWeight: theme.typography.weight.medium,
    marginTop: theme.spacing.md,
    backgroundColor: 'rgba(0, 0, 0, 0.6)',
    paddingHorizontal: theme.spacing.md,
    paddingVertical: 4,
    borderRadius: theme.radius.full,
  },
  footer: {
    padding: theme.spacing.lg,
    paddingBottom: theme.spacing.xl,
    backgroundColor: '#0F172A',
  },
  countBadge: {
    alignItems: 'center',
    marginBottom: theme.spacing.md,
  },
  count: {
    color: '#FFFFFF',
    fontSize: theme.typography.size.xs,
    fontWeight: theme.typography.weight.medium,
  },
  footerActions: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  sideSpacer: {
    width: 80,
  },
  shutterOuter: {
    width: 72,
    height: 72,
    borderRadius: 36,
    borderWidth: 4,
    borderColor: '#FFFFFF',
    alignItems: 'center',
    justifyContent: 'center',
  },
  captureButton: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: theme.colors.forest[600],
  },
  sideAction: {
    width: 80,
    alignItems: 'flex-end',
  },
  continueButton: {
    backgroundColor: theme.colors.forest[600],
    borderRadius: theme.radius.md,
    paddingVertical: 10,
    paddingHorizontal: 14,
    minHeight: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  continueButtonText: {
    color: '#FFFFFF',
    fontWeight: theme.typography.weight.bold,
    fontSize: theme.typography.size.xs,
  },
  primaryButton: {
    flex: 1,
    backgroundColor: theme.colors.forest[600],
    borderRadius: theme.radius.md,
    paddingVertical: 14,
    alignItems: 'center',
    minHeight: 48,
  },
  primaryButtonText: {
    color: '#FFFFFF',
    fontWeight: theme.typography.weight.bold,
    fontSize: theme.typography.size.sm,
  },
  secondaryButton: {
    flex: 1,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.3)',
    borderRadius: theme.radius.md,
    paddingVertical: 14,
    alignItems: 'center',
    minHeight: 48,
  },
  secondaryButtonText: {
    color: '#FFFFFF',
    fontWeight: theme.typography.weight.semibold,
    fontSize: theme.typography.size.sm,
  },
  disabled: {
    opacity: 0.4,
  },
});
