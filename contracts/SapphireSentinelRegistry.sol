// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title  SapphireSentinelRegistry
/// @notice Robinhood Chain testnet registry for agent payment mandates and
///         policy-screened payment receipts.
/// @dev    This contract never moves funds and never executes trades. It is an
///         auditable anchoring layer for off-chain x402 payments, private risk
///         proofs, and dry-run order drafts.
/// @custom:deployment Robinhood Chain testnet (46630)
///   0x2EBB91F7B376cB821d90ac4A7d77B0d06b70B36F
/// @custom:creation-tx
///   0xc53ab8fc8cdab4ce7ef5f09fd56fc564756fd8d5e5b7c0396238878d6cc84975
contract SapphireSentinelRegistry {
    struct Mandate {
        address controller;
        address agent;
        uint96 maxSpendAtomic;
        uint96 spentAtomic;
        uint32 evaluationCount;
        uint64 expiresAt;
        bytes32 policyHash;
        bool revoked;
    }

    struct Receipt {
        bytes32 mandateId;
        address payer;
        uint96 amountAtomic;
        bytes32 resourceHash;
        bytes32 resultHash;
        bytes32 riskHash;
        bytes32 privacyCommitment;
        uint64 timestamp;
        uint64 decisionNonce;
        bool approved;
    }

    address public operator;
    /// @notice Pending operator awaiting `acceptOperator()` confirmation.
    address public pendingOperator;

    mapping(bytes32 => Mandate) public mandates;
    mapping(bytes32 => Receipt) public receipts;
    mapping(bytes32 => mapping(uint64 => bool)) public usedDecisionNonces;

    event MandateRegistered(
        bytes32 indexed mandateId,
        address indexed controller,
        address indexed agent,
        uint96 maxSpendAtomic,
        uint64 expiresAt,
        bytes32 policyHash
    );
    event MandateRevoked(bytes32 indexed mandateId);
    event PaymentEvaluated(
        bytes32 indexed receiptId,
        bytes32 indexed mandateId,
        address indexed payer,
        bool approved,
        uint96 amountAtomic,
        bytes32 resourceHash,
        bytes32 resultHash,
        bytes32 riskHash,
        bytes32 privacyCommitment,
        uint64 decisionNonce
    );
    event OperatorTransferStarted(address indexed previousOperator, address indexed newOperator);
    event OperatorTransferred(address indexed previousOperator, address indexed newOperator);

    modifier onlyOperator() {
        require(msg.sender == operator, "Not operator");
        _;
    }

    constructor() {
        operator = msg.sender;
    }

    function registerMandate(
        bytes32 mandateId,
        address controller,
        address agent,
        uint96 maxSpendAtomic,
        uint64 expiresAt,
        bytes32 policyHash
    ) external onlyOperator {
        require(mandateId != bytes32(0), "Zero mandate");
        require(controller != address(0), "Zero controller");
        require(agent != address(0), "Zero agent");
        require(maxSpendAtomic > 0, "Zero spend");
        require(expiresAt > block.timestamp, "Expired mandate");
        require(policyHash != bytes32(0), "Zero policy");
        require(mandates[mandateId].controller == address(0), "Mandate exists");

        mandates[mandateId] = Mandate({
            controller: controller,
            agent: agent,
            maxSpendAtomic: maxSpendAtomic,
            spentAtomic: 0,
            evaluationCount: 0,
            expiresAt: expiresAt,
            policyHash: policyHash,
            revoked: false
        });

        emit MandateRegistered(mandateId, controller, agent, maxSpendAtomic, expiresAt, policyHash);
    }

    function revokeMandate(bytes32 mandateId) external onlyOperator {
        Mandate storage mandate = mandates[mandateId];
        require(mandate.controller != address(0), "Unknown mandate");
        mandate.revoked = true;
        emit MandateRevoked(mandateId);
    }

    function recordPaymentEvaluation(
        bytes32 receiptId,
        bytes32 mandateId,
        address payer,
        uint96 amountAtomic,
        bytes32 resourceHash,
        bytes32 resultHash,
        bytes32 riskHash,
        bytes32 privacyCommitment,
        uint64 decisionNonce,
        bool approved
    ) external onlyOperator {
        require(receiptId != bytes32(0), "Zero receipt");
        require(receipts[receiptId].mandateId == bytes32(0), "Receipt exists");
        require(payer != address(0), "Zero payer");
        require(resourceHash != bytes32(0), "Zero resource");
        require(resultHash != bytes32(0), "Zero result");
        require(riskHash != bytes32(0), "Zero risk");
        require(privacyCommitment != bytes32(0), "Zero privacy");
        require(decisionNonce != 0, "Zero nonce");

        Mandate storage mandate = mandates[mandateId];
        require(mandate.controller != address(0), "Unknown mandate");
        require(!mandate.revoked, "Mandate revoked");
        require(block.timestamp <= mandate.expiresAt, "Mandate expired");
        require(!usedDecisionNonces[mandateId][decisionNonce], "Nonce used");
        usedDecisionNonces[mandateId][decisionNonce] = true;

        if (approved) {
            require(amountAtomic > 0, "Zero amount");
            require(
                mandate.spentAtomic + amountAtomic <= mandate.maxSpendAtomic,
                "Spend limit exceeded"
            );
            mandate.spentAtomic += amountAtomic;
        }
        mandate.evaluationCount += 1;

        receipts[receiptId] = Receipt({
            mandateId: mandateId,
            payer: payer,
            amountAtomic: amountAtomic,
            resourceHash: resourceHash,
            resultHash: resultHash,
            riskHash: riskHash,
            privacyCommitment: privacyCommitment,
            timestamp: uint64(block.timestamp),
            decisionNonce: decisionNonce,
            approved: approved
        });

        emit PaymentEvaluated(
            receiptId,
            mandateId,
            payer,
            approved,
            amountAtomic,
            resourceHash,
            resultHash,
            riskHash,
            privacyCommitment,
            decisionNonce
        );
    }

    function remainingSpend(bytes32 mandateId) external view returns (uint96) {
        Mandate memory mandate = mandates[mandateId];
        if (mandate.controller == address(0) || mandate.spentAtomic >= mandate.maxSpendAtomic) {
            return 0;
        }
        return mandate.maxSpendAtomic - mandate.spentAtomic;
    }

    function isMandateActive(bytes32 mandateId) external view returns (bool) {
        Mandate memory mandate = mandates[mandateId];
        return mandate.controller != address(0)
            && !mandate.revoked
            && block.timestamp <= mandate.expiresAt;
    }

    function transferOperator(address newOperator) external onlyOperator {
        require(newOperator != address(0), "Zero address");
        pendingOperator = newOperator;
        emit OperatorTransferStarted(operator, newOperator);
    }

    function acceptOperator() external {
        require(msg.sender == pendingOperator, "Not pending operator");
        address previousOperator = operator;
        operator = pendingOperator;
        pendingOperator = address(0);
        emit OperatorTransferred(previousOperator, operator);
    }
}
