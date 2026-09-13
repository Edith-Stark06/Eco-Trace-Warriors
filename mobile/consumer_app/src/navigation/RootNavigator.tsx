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
import { theme } from '../theme';

const Stack = createNativeStackNavigator<RootStackParamList>();

export function RootNavigator() {
  const { status } = useAuth();

  if (status === 'loading') {
    return <LoadingIndicator label="Starting EcoTrace…" />;
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
          <>
            <Stack.Screen name="Login" component={LoginScreen} options={{ headerShown: false }} />
            <Stack.Screen name="Register" component={RegisterScreen} options={{ title: 'Create account' }} />
          </>
        ) : (
          <>
            <Stack.Screen name="Dashboard" component={DashboardScreen} options={{ headerShown: false }} />
            <Stack.Screen name="ReportWaste" component={ReportWasteScreen} options={{ title: 'Report E-Waste' }} />
            <Stack.Screen name="Scan" component={ScanScreen} options={{ title: 'Verify a Device' }} />
            <Stack.Screen name="DevicePassport" component={DevicePassportScreen} options={{ title: 'Device Passport' }} />
            <Stack.Screen name="Rewards" component={RewardsScreen} options={{ title: 'Rewards & GreenCoins' }} />
            <Stack.Screen name="SubmissionHistory" component={SubmissionHistoryScreen} options={{ title: 'My Submissions' }} />
            <Stack.Screen name="Education" component={EducationScreen} options={{ title: 'Learn' }} />
            <Stack.Screen name="Profile" component={ProfileScreen} options={{ title: 'Profile' }} />
          </>
        )}
      </Stack.Navigator>
    </NavigationContainer>
  );
}
