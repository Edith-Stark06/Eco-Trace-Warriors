import React, { useRef, useState } from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { ErrorState } from '../components/ErrorState';

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
export function CaptureScreen({ navigation }: Props) {
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
    navigation.navigate('RegisterDevice', { images: shots });
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
      <View style={styles.footer}>
        <Text style={styles.count} accessibilityLiveRegion="polite">
          {shots.length} photo(s) captured
        </Text>
        <View style={styles.footerActions}>
          <Pressable
            style={styles.captureButton}
            onPress={handleCapture}
            accessibilityRole="button"
            accessibilityLabel="Take photo"
            testID="capture-shutter-button"
          />
          <Pressable
            style={[styles.primaryButton, shots.length === 0 && styles.disabled]}
            onPress={handleContinue}
            disabled={shots.length === 0}
            accessibilityRole="button"
            accessibilityLabel="Continue to device registration"
            accessibilityState={{ disabled: shots.length === 0 }}
          >
            <Text style={styles.primaryButtonText}>Continue</Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000000' },
  camera: { flex: 1 },
  preview: { flex: 1 },
  previewActions: { flexDirection: 'row', gap: 12, padding: 16, backgroundColor: '#000000' },
  footer: { padding: 16, backgroundColor: '#111827' },
  count: { color: '#FFFFFF', textAlign: 'center', marginBottom: 12 },
  footerActions: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-around' },
  captureButton: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: '#FFFFFF',
    borderWidth: 4,
    borderColor: '#2E7D32',
  },
  primaryButton: { backgroundColor: '#2E7D32', borderRadius: 8, paddingVertical: 12, paddingHorizontal: 20, minHeight: 44 },
  primaryButtonText: { color: '#FFFFFF', fontWeight: '600' },
  secondaryButton: { flex: 1, borderWidth: 1, borderColor: '#FFFFFF', borderRadius: 8, paddingVertical: 12, alignItems: 'center', minHeight: 44 },
  secondaryButtonText: { color: '#FFFFFF', fontWeight: '600' },
  disabled: { opacity: 0.5 },
});
