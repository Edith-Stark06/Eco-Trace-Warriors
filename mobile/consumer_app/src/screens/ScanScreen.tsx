import React, { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { CameraView, useCameraPermissions, type BarcodeScanningResult } from 'expo-camera';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { ErrorState } from '../components/ErrorState';
import { resolveScannedCode } from '../lib/ecoQr';
import { theme } from '../theme';

const INVALID_QR_MESSAGE = 'Invalid EcoTrace QR. Please scan a valid EcoTrace device QR.';

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

    const scanned = resolveScannedCode(code);
    if (scanned.kind === 'invalid') {
      setLastError(INVALID_QR_MESSAGE);
      return;
    }

    setHandled(true);
    setLastError(null);
    navigation.replace('DevicePassport', { deviceId: scanned.identifier });
  };

  return (
    <View style={styles.container}>
      <CameraView
        style={styles.camera}
        facing="back"
        barcodeScannerSettings={{ barcodeTypes: ['qr', 'code128', 'ean13'] }}
        onBarcodeScanned={handled ? undefined : handleScan}
      />

      {/* Viewfinder Overlay with corner HUD reticle */}
      <View style={styles.overlay}>
        <View style={styles.titleBanner}>
          <Text style={styles.titleText}>Scan device QR</Text>
          <Text style={styles.subtitleText}>Scan the QR displayed by the EcoTrace collector.</Text>
        </View>

        <View style={styles.reticleContainer}>
          <View style={styles.frame}>
            {/* Corner Bracket Accents */}
            <View style={[styles.corner, styles.cornerTL]} />
            <View style={[styles.corner, styles.cornerTR]} />
            <View style={[styles.corner, styles.cornerBL]} />
            <View style={[styles.corner, styles.cornerBR]} />
          </View>
        </View>

        <View style={styles.instructionBadge}>
          <Text style={styles.instructionIcon}>🔍</Text>
          <Text style={styles.hint}>Align the device QR code within the frame</Text>
        </View>

        {lastError ? (
          <View style={styles.errorBox}>
            <Text style={styles.error} accessibilityRole="alert">
              {lastError}
            </Text>
          </View>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#000000',
  },
  camera: {
    flex: 1,
  },
  titleBanner: {
    position: 'absolute',
    top: 64,
    left: theme.spacing.lg,
    right: theme.spacing.lg,
    alignItems: 'center',
  },
  titleText: {
    color: '#FFFFFF',
    fontSize: theme.typography.size.lg,
    fontWeight: theme.typography.weight.bold,
    letterSpacing: 0.3,
  },
  subtitleText: {
    color: 'rgba(255, 255, 255, 0.75)',
    fontSize: theme.typography.size.xs,
    marginTop: 4,
    textAlign: 'center',
  },
  overlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    alignItems: 'center',
    justifyContent: 'center',
    padding: theme.spacing.lg,
  },
  reticleContainer: {
    width: 250,
    height: 250,
    alignItems: 'center',
    justifyContent: 'center',
  },
  frame: {
    width: 240,
    height: 240,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.25)',
    borderRadius: theme.radius.lg,
    position: 'relative',
  },
  corner: {
    position: 'absolute',
    width: 24,
    height: 24,
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
  instructionBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(15, 23, 42, 0.85)',
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    borderRadius: theme.radius.full,
    marginTop: theme.spacing.xl,
    gap: 8,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.1)',
  },
  instructionIcon: {
    fontSize: 14,
  },
  hint: {
    color: '#FFFFFF',
    fontSize: theme.typography.size.xs,
    fontWeight: theme.typography.weight.medium,
  },
  errorBox: {
    backgroundColor: 'rgba(153, 27, 27, 0.9)',
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.xs,
    borderRadius: theme.radius.sm,
    marginTop: theme.spacing.md,
  },
  error: {
    color: '#FFFFFF',
    fontSize: theme.typography.size.xs,
    fontWeight: theme.typography.weight.medium,
  },
});
