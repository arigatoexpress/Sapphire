// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

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

    event SignalPublished(uint256 indexed id, string symbol, uint8 direction, uint16 confidence);
    event SignalVerified(uint256 indexed id, bytes32 proofHash);

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

    function transferOperator(address newOperator) external onlyOperator {
        require(newOperator != address(0), "Zero address");
        operator = newOperator;
    }
}
