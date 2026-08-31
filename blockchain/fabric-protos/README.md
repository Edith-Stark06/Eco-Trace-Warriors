# Vendored Hyperledger Fabric Gateway protobuf definitions

These `.proto` files are copied **verbatim, unmodified** from the official
[`hyperledger/fabric-protos`](https://github.com/hyperledger/fabric-protos)
repository (`main` branch), licensed Apache-2.0 by the Hyperledger Fabric
contributors.

## Why they are vendored here

Hyperledger Fabric does not publish an official Python client SDK for the
Fabric Gateway service (only Go, Node.js and Java — see
[`hyperledger/fabric-gateway`](https://github.com/hyperledger/fabric-gateway)).
The Gateway is a plain gRPC service, so a Python client talks to it directly
over gRPC using these protobuf message/service definitions, compiled with
`grpcio-tools`. This is the standard workaround pattern used by every
unofficial Python Fabric Gateway client, because no other correct production
dependency exists for this language (verified via web search during P6.2 —
see `reports/P6_2_FABRIC_GATEWAY_INTEGRATION.md`).

## Files

Only the transitive closure of `.proto` files needed to compile
`gateway/gateway.proto` (the `Gateway` service: `Endorse`, `Submit`,
`CommitStatus`, `Evaluate`, `ChaincodeEvents`) is vendored — not the full
`fabric-protos` repository.

## Regenerating the compiled Python stubs

The compiled output lives at `intelligence/device_ai/devices/fabric_pb/`
and is committed (there is no protoc build step in this repository's test/CI
pipeline). To regenerate it after updating these source files:

```bash
cd intelligence/device_ai
python -m pip install grpcio grpcio-tools
SRC=../../blockchain/fabric-protos
OUT=devices/fabric_pb
python -m grpc_tools.protoc -I"$SRC" --python_out="$OUT" --grpc_python_out="$OUT" \
  "$SRC/gateway/gateway.proto" \
  "$SRC/peer/proposal.proto" \
  "$SRC/peer/proposal_response.proto" \
  "$SRC/peer/transaction.proto" \
  "$SRC/peer/chaincode.proto" \
  "$SRC/peer/chaincode_event.proto" \
  "$SRC/peer/policy.proto" \
  "$SRC/peer/events.proto" \
  "$SRC/common/common.proto" \
  "$SRC/common/policies.proto" \
  "$SRC/common/ledger.proto" \
  "$SRC/common/configtx.proto" \
  "$SRC/msp/identities.proto" \
  "$SRC/msp/msp_principal.proto" \
  "$SRC/orderer/ab.proto" \
  "$SRC/ledger/rwset/rwset.proto"
```

`__init__.py` files must be (re-)added to each generated package directory
(`gateway/`, `peer/`, `common/`, `msp/`, `orderer/`, `ledger/`,
`ledger/rwset/`) — `protoc` does not create them.
