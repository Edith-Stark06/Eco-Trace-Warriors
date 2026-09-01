import React, { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { CameraView, useCameraPermissions, type BarcodeScanningResult } from 'expo-camera';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { ErrorState } from '../components/ErrorState';

type Props = NativeStackScreenProps<RootStackParamList, 'Scan'>;

/** Scans a device's QR code to look up its passport/trust status. */
export function ScanScreen({ navigation }: Props) {
  const [permission, requestPermission] = useCameraPermissions();
  const [handled, setHandled] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);

  if (!permission) {
    return <View style={styles.container} />;
  }

  if (!permission.granted) {
    return (
      <ErrorState
        message={
          permission.canAskAgain
            ? 'Camera access is required to scan a device code.'
            : 'Camera access was denied. Enable it in system settings to continue.'
        }
        onRetry={permission.canAskAgain ? requestPermission : undefined}
      />
    );
  }

  const handleScan = (result: BarcodeScanningResult) => {
    if (handled) return;
    const code = result.data?.trim();
    if (!code) {
      setLastError('Unreadable code — try again with better lighting.');
      return;
    }
    setHandled(true);
    navigation.replace('DevicePassport', { deviceId: code });
  };

  return (
    <View style={styles.container}>
      <CameraView
        style={styles.camera}
        facing="back"
        barcodeScannerSettings={{ barcodeTypes: ['qr', 'code128', 'ean13'] }}
        onBarcodeScanned={handled ? undefined : handleScan}
      />
      <View style={styles.overlay}>
        <View style={styles.frame} />
        <Text style={styles.hint}>Align the device QR code within the frame</Text>
        {lastError ? (
          <Text style={styles.error} accessibilityRole="alert">
            {lastError}
          </Text>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000000' },
  camera: { flex: 1 },
  overlay: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, alignItems: 'center', justifyContent: 'center' },
  frame: { width: 240, height: 240, borderWidth: 3, borderColor: '#4ADE80', borderRadius: 12 },
  hint: { color: '#FFFFFF', marginTop: 16, fontSize: 14 },
  error: { color: '#FCA5A5', marginTop: 8, fontSize: 13 },
});
