import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import { RegisterScreen } from './RegisterScreen';
import * as AuthContextModule from '../auth/AuthContext';

jest.mock('../auth/AuthContext', () => ({
  useAuth: jest.fn(),
}));

const useAuthMock = AuthContextModule.useAuth as jest.Mock;

// See collector_app/src/screens/LoginScreen.test.tsx for why render()/
// fireEvent must be awaited on this React 19 / test-renderer stack.
describe('RegisterScreen', () => {
  it('keeps the submit button disabled until the form is valid', async () => {
    useAuthMock.mockReturnValue({ register: jest.fn(), error: null, clearError: jest.fn() });

    const { getByTestId } = await render(<RegisterScreen navigation={{ navigate: jest.fn() } as never} route={{} as never} />);
    const submit = getByTestId('register-submit-button');
    expect(submit.props.accessibilityState.disabled).toBe(true);

    await fireEvent.changeText(getByTestId('register-name-input'), 'Asha Kumar');
    await fireEvent.changeText(getByTestId('register-email-input'), 'asha@ecotrace.test');
    await fireEvent.changeText(getByTestId('register-password-input'), 'Str0ngPass!');
    await fireEvent.changeText(getByTestId('register-confirm-password-input'), 'Str0ngPass!');

    expect(getByTestId('register-submit-button').props.accessibilityState.disabled).toBe(false);
  });

  it('stays disabled when passwords do not match', async () => {
    useAuthMock.mockReturnValue({ register: jest.fn(), error: null, clearError: jest.fn() });

    const { getByTestId } = await render(<RegisterScreen navigation={{ navigate: jest.fn() } as never} route={{} as never} />);
    await fireEvent.changeText(getByTestId('register-name-input'), 'Asha Kumar');
    await fireEvent.changeText(getByTestId('register-email-input'), 'asha@ecotrace.test');
    await fireEvent.changeText(getByTestId('register-password-input'), 'Str0ngPass!');
    await fireEvent.changeText(getByTestId('register-confirm-password-input'), 'Different!');

    expect(getByTestId('register-submit-button').props.accessibilityState.disabled).toBe(true);
  });

  it('calls register with the entered fields once the form is valid', async () => {
    const register = jest.fn().mockResolvedValue(undefined);
    useAuthMock.mockReturnValue({ register, error: null, clearError: jest.fn() });

    const { getByTestId } = await render(<RegisterScreen navigation={{ navigate: jest.fn() } as never} route={{} as never} />);
    await fireEvent.changeText(getByTestId('register-name-input'), 'Asha Kumar');
    await fireEvent.changeText(getByTestId('register-email-input'), 'asha@ecotrace.test');
    await fireEvent.changeText(getByTestId('register-password-input'), 'Str0ngPass!');
    await fireEvent.changeText(getByTestId('register-confirm-password-input'), 'Str0ngPass!');
    await fireEvent.press(getByTestId('register-submit-button'));

    expect(register).toHaveBeenCalledWith({
      fullName: 'Asha Kumar',
      email: 'asha@ecotrace.test',
      password: 'Str0ngPass!',
      confirmPassword: 'Str0ngPass!',
    });
  });
});
