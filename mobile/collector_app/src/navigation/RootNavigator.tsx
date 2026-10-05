import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { useAuth } from '../auth/AuthContext';
import { LoadingIndicator } from '../components/LoadingIndicator';
import { LoginScreen } from '../screens/LoginScreen';
import { DashboardScreen } from '../screens/DashboardScreen';
import { CaptureScreen } from '../screens/CaptureScreen';
import { ScanScreen } from '../screens/ScanScreen';
import { RegisterDeviceScreen } from '../screens/RegisterDeviceScreen';
import { SubmissionHistoryScreen } from '../screens/SubmissionHistoryScreen';
import { SubmissionDetailScreen } from '../screens/SubmissionDetailScreen';
import { ProfileScreen } from '../screens/ProfileScreen';
import type { RootStackParamList } from './types';
import { theme } from '../theme';

const Stack = createNativeStackNavigator<RootStackParamList>();

export function RootNavigator() {
  const { status } = useAuth();

  if (status === 'loading') {
    return <LoadingIndicator label="Starting EcoTrace Collector…" />;
  }

  return (
    <NavigationContainer>
      <Stack.Navigator
        screenOptions={{
          headerTintColor: theme.colors.forest[700],
          headerTitleStyle: {
            fontWeight: '700',
            fontSize: 17,
            color: theme.colors.slate[900],
          },
          headerStyle: {
            backgroundColor: theme.colors.surface,
          },
          headerShadowVisible: false,
          contentStyle: {
            backgroundColor: theme.colors.background.app,
          },
        }}
      >
        {status === 'unauthenticated' ? (
          <Stack.Screen name="Login" component={LoginScreen} options={{ headerShown: false }} />
        ) : (
          <>
            <Stack.Screen name="Dashboard" component={DashboardScreen} options={{ headerShown: false }} />
            <Stack.Screen name="Capture" component={CaptureScreen} options={{ title: 'Capture Device' }} />
            <Stack.Screen name="Scan" component={ScanScreen} options={{ title: 'Scan Device' }} />
            <Stack.Screen
              name="RegisterDevice"
              component={RegisterDeviceScreen}
              options={{ title: 'Register Device' }}
            />
            <Stack.Screen
              name="SubmissionHistory"
              component={SubmissionHistoryScreen}
              options={{ title: 'Submission History' }}
            />
            <Stack.Screen
              name="SubmissionDetail"
              component={SubmissionDetailScreen}
              options={{ title: 'Submission' }}
            />
            <Stack.Screen name="Profile" component={ProfileScreen} options={{ title: 'Profile' }} />
          </>
        )}
      </Stack.Navigator>
    </NavigationContainer>
  );
}
