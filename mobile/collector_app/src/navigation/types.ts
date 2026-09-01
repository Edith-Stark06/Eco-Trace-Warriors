export type RootStackParamList = {
  Login: undefined;
  Dashboard: undefined;
  Capture: undefined;
  Scan: undefined;
  RegisterDevice: { images: { uri: string; name: string; type: string }[] };
  SubmissionHistory: undefined;
  SubmissionDetail: { submissionId: string };
  Profile: undefined;
};
