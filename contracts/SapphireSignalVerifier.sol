// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title  SapphireSignalVerifier
/// @notice On-chain registry for trading signals published by an off-chain
///         operator, with a reserved `proofHash` slot for future zk-verifiable
///         computation.
/// @dev    Operator-only mutators. Role transfer is two-step (`pendingOperator`
///         must call `acceptOperator()`) to prevent permanent bricking from a
///         typo or transfer to an unowned address. See the
///         `docs/security/contracts-review-2026-04-26.md` follow-up section for
///         the rationale.
contract SapphireSignalVerifier {
    struct Signal {
        bytes32 strategyId;     // Hash of strategy name
        string symbol;          // e.g., "BTC-USD"
        uint8 direction;        // 0=neutral, 1=long, 2=short
        uint16 confidence;      // 0-10000 (basis points)
        uint256 timestamp;
        bytes32 proofHash;      // ZK proof hash (for future verification)
    }

    mapping(uint256 => Signal) public signals;
    uint256 public signalCount;
    address public operator;
    /// @notice Pending operator awaiting `acceptOperator()` confirmation.
    /// @dev    Two-step transfer guard. `address(0)` means no transfer is in flight.
    address public pendingOperator;

    event SignalPublished(uint256 indexed id, string symbol, uint8 direction, uint16 confidence);
    event SignalVerified(uint256 indexed id, bytes32 proofHash);
    /// @notice Emitted when `transferOperator` nominates a new operator.
    /// @dev    The new operator must call `acceptOperator()` before takeover completes.
    event OperatorTransferStarted(address indexed previousOperator, address indexed newOperator);
    /// @notice Emitted when `acceptOperator` finalises the role transfer.
    event OperatorTransferred(address indexed previousOperator, address indexed newOperator);

    modifier onlyOperator() {
        require(msg.sender == operator, "Not operator");
        _;
    }

    constructor() {
        operator = msg.sender;
    }

    function publishSignal(
        bytes32 strategyId,
        string calldata symbol,
        uint8 direction,
        uint16 confidence,
        bytes32 proofHash
    ) external onlyOperator returns (uint256) {
        uint256 id = signalCount++;
        signals[id] = Signal(strategyId, symbol, direction, confidence, block.timestamp, proofHash);
        emit SignalPublished(id, symbol, direction, confidence);
        return id;
    }

    function getSignal(uint256 id) external view returns (Signal memory) {
        return signals[id];
    }

    function getLatestSignals(uint256 count) external view returns (Signal[] memory) {
        uint256 start = signalCount > count ? signalCount - count : 0;
        Signal[] memory result = new Signal[](signalCount - start);
        for (uint256 i = start; i < signalCount; i++) {
            result[i - start] = signals[i];
        }
        return result;
    }

    /// @notice Nominates `newOperator` as the pending operator.
    /// @dev    Step 1 of the two-step transfer. The current operator stays in
    ///         place until `newOperator` calls `acceptOperator()`. Calling this
    ///         with a different address before acceptance overwrites the
    ///         pending nominee. Zero address is rejected; to cancel an
    ///         in-flight transfer the operator should renominate themselves
    ///         and call `acceptOperator()` from the same key.
    /// @param  newOperator The address to nominate as the next operator. Must
    ///         not be the zero address.
    function transferOperator(address newOperator) external onlyOperator {
        require(newOperator != address(0), "Zero address");
        pendingOperator = newOperator;
        emit OperatorTransferStarted(operator, newOperator);
    }

    /// @notice Finalises a pending operator transfer initiated by `transferOperator`.
    /// @dev    Step 2 of the two-step transfer. Must be called by the address
    ///         previously passed to `transferOperator`. Clears `pendingOperator`
    ///         on success. This guards against typos and transfers to addresses
    ///         whose private key is unknown (e.g. an unfunded multisig) — if
    ///         the new operator cannot sign `acceptOperator`, the role stays
    ///         with the existing operator.
    function acceptOperator() external {
        require(msg.sender == pendingOperator, "Not pending operator");
        address previousOperator = operator;
        operator = pendingOperator;
        pendingOperator = address(0);
        emit OperatorTransferred(previousOperator, operator);
    }
}
