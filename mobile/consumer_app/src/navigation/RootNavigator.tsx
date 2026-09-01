import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { useAuth } from '../auth/AuthContext';
import { LoadingIndicator } from '../components/LoadingIndicator';
import { LoginScreen } from '../screens/LoginScreen';
import { RegisterScreen } from '../screens/RegisterScreen';
import { DashboardScreen } from '../screens/DashboardScreen';
import { ReportWasteScreen } from '../screens/ReportWasteScreen';
import { ScanScreen } from '../screens/ScanScreen';
import { DevicePassportScreen } from '../screens/DevicePassportScreen';
import { RewardsScreen } from '../screens/RewardsScreen';
import { SubmissionHistoryScreen } from '../screens/SubmissionHistoryScreen';
import { EducationScreen } from '../screens/EducationScreen';
import { ProfileScreen } from '../screens/ProfileScreen';
import type { RootStackParamList } from './types';

const Stack = createNativeStackNavigator<RootStackParamList>();

export function RootNavigator() {
  const { status } = useAuth();

  if (status === 'loading') {
    return <LoadingIndicator label="Starting EcoTrace…" />;
  }

  return (
    <NavigationContainer>
      <Stack.Navigator screenOptions={{ headerTintColor: '#1B5E20' }}>
        {status === 'unauthenticated' ? (
          <>
            <Stack.Screen name="Login" component={LoginScreen} options={{ headerShown: false }} />
            <Stack.Screen name="Register" component={RegisterScreen} options={{ title: 'Create account' }} />
          </>
        ) : (
          <>
            <Stack.Screen name="Dashboard" component={DashboardScreen} options={{ headerShown: false }} />
            <Stack.Screen name="ReportWaste" component={ReportWasteScreen} options={{ title: 'Report e-waste' }} />
            <Stack.Screen name="Scan" component={ScanScreen} options={{ title: 'Verify a device' }} />
            <Stack.Screen name="DevicePassport" component={DevicePassportScreen} options={{ title: 'Device passport' }} />
            <Stack.Screen name="Rewards" component={RewardsScreen} options={{ title: 'Rewards' }} />
            <Stack.Screen name="SubmissionHistory" component={SubmissionHistoryScreen} options={{ title: 'My submissions' }} />
            <Stack.Screen name="Education" component={EducationScreen} options={{ title: 'Learn' }} />
            <Stack.Screen name="Profile" component={ProfileScreen} options={{ title: 'Profile' }} />
          </>
        )}
      </Stack.Navigator>
    </NavigationContainer>
  );
}
