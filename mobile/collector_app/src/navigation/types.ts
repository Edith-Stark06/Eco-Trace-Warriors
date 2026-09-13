export type RootStackParamList = {
  Login: undefined;
  Dashboard: undefined;
  /**
   * `submissionId` is present when Capture was launched from a specific
   * submission's pickup (SubmissionDetailScreen's "Register device" action)
   * so the resulting device can be cross-referenced with that submission
   * (P10.1) — see docs/engineering/03_ARCHITECTURE.md. Absent for the
   * standalone Dashboard -> Capture flow, which registers a device with no
   * submission context, exactly as before.
   */
  Capture: { submissionId?: string } | undefined;
  Scan: undefined;
  RegisterDevice: { images: { uri: string; name: string; type: string }[]; submissionId?: string };
  SubmissionHistory: undefined;
  SubmissionDetail: { submissionId: string };
  Profile: undefined;
};
