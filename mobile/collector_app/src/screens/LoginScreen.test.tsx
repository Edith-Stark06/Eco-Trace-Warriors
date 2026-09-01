import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import { LoginScreen } from './LoginScreen';
import * as AuthContextModule from '../auth/AuthContext';

jest.mock('../auth/AuthContext', () => ({
  useAuth: jest.fn(),
}));

const useAuthMock = AuthContextModule.useAuth as jest.Mock;

// @testing-library/react-native v14 on this React 19 / test-renderer stack
// makes render() AND fireEvent.* return Promises — every interaction below
// must be awaited or React logs "overlapping act() calls" and the query
// runs against a stale tree.
describe('LoginScreen', () => {
  it('calls login with the entered email and password', async () => {
    const login = jest.fn().mockResolvedValue(undefined);
    useAuthMock.mockReturnValue({ login, error: null, clearError: jest.fn() });

    const { getByTestId } = await render(<LoginScreen />);
    await fireEvent.changeText(getByTestId('login-email-input'), 'collector@ecotrace.test');
    await fireEvent.changeText(getByTestId('login-password-input'), 'Admin@123');
    await fireEvent.press(getByTestId('login-submit-button'));

    await waitFor(() => {
      expect(login).toHaveBeenCalledWith('collector@ecotrace.test', 'Admin@123');
    });
  });

  it('does not call login when the form is empty', async () => {
    const login = jest.fn();
    useAuthMock.mockReturnValue({ login, error: null, clearError: jest.fn() });

    const { getByTestId } = await render(<LoginScreen />);
    await fireEvent.press(getByTestId('login-submit-button'));

    expect(login).not.toHaveBeenCalled();
  });

  it('renders an authentication error from context', async () => {
    useAuthMock.mockReturnValue({
      login: jest.fn(),
      error: 'Invalid credentials',
      clearError: jest.fn(),
    });

    const { getByText } = await render(<LoginScreen />);
    expect(getByText('Invalid credentials')).toBeTruthy();
  });
});
