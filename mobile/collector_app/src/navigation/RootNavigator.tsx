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

const Stack = createNativeStackNavigator<RootStackParamList>();

export function RootNavigator() {
  const { status } = useAuth();

  if (status === 'loading') {
    return <LoadingIndicator label="Starting EcoTrace Collector…" />;
  }

  return (
    <NavigationContainer>
      <Stack.Navigator screenOptions={{ headerTintColor: '#1B5E20' }}>
        {status === 'unauthenticated' ? (
          <Stack.Screen name="Login" component={LoginScreen} options={{ headerShown: false }} />
        ) : (
          <>
            <Stack.Screen name="Dashboard" component={DashboardScreen} options={{ headerShown: false }} />
            <Stack.Screen name="Capture" component={CaptureScreen} options={{ title: 'Capture device' }} />
            <Stack.Screen name="Scan" component={ScanScreen} options={{ title: 'Scan device' }} />
            <Stack.Screen
              name="RegisterDevice"
              component={RegisterDeviceScreen}
              options={{ title: 'Register device' }}
            />
            <Stack.Screen
              name="SubmissionHistory"
              component={SubmissionHistoryScreen}
              options={{ title: 'Submission history' }}
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
