// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title  SapphirePaymentGate
/// @notice Micropayment + monthly subscription gate. Counterpart to the
///         off-chain x402 middleware in `lib/payments/x402_middleware.py`.
/// @dev    Treasury role is two-step (`pendingTreasury` must call
///         `acceptTreasury()`) to prevent permanent bricking from a typo or
///         transfer to an unowned address. Setters reject zero prices to avoid
///         a DoS via division-by-zero on `payPerSignal()` and to avoid an
///         "anyone subscribes for free" bug on `subscribe()`. See the
///         `docs/security/contracts-review-2026-04-26.md` follow-up section
///         for the rationale.
contract SapphirePaymentGate {
    address public treasury;
    /// @notice Pending treasury awaiting `acceptTreasury()` confirmation.
    /// @dev    Two-step transfer guard. `address(0)` means no transfer is in flight.
    address public pendingTreasury;
    mapping(address => uint256) public credits;
    mapping(address => uint256) public subscriptionExpiry;

    uint256 public pricePerSignal = 0.001 ether;    // ~$0.003
    uint256 public monthlySubscription = 0.1 ether; // ~$300

    event PaymentReceived(address indexed from, uint256 amount, string service);
    event SubscriptionActivated(address indexed subscriber, uint256 expiry);
    event CreditsConsumed(address indexed user, uint256 remaining);
    /// @notice Emitted when `transferTreasury` nominates a new treasury.
    /// @dev    The new treasury must call `acceptTreasury()` before takeover completes.
    event TreasuryTransferStarted(address indexed previousTreasury, address indexed newTreasury);
    /// @notice Emitted when `acceptTreasury` finalises the role transfer.
    event TreasuryTransferred(address indexed previousTreasury, address indexed newTreasury);

    modifier onlyTreasury() {
        require(msg.sender == treasury, "Not treasury");
        _;
    }

    constructor() {
        treasury = msg.sender;
    }

    function payPerSignal() external payable {
        require(msg.value >= pricePerSignal, "Insufficient payment");
        credits[msg.sender] += msg.value / pricePerSignal;
        emit PaymentReceived(msg.sender, msg.value, "signal");
    }

    function subscribe() external payable {
        require(msg.value >= monthlySubscription, "Insufficient payment");
        uint256 current = subscriptionExpiry[msg.sender];
        uint256 base = current > block.timestamp ? current : block.timestamp;
        subscriptionExpiry[msg.sender] = base + 30 days;
        emit SubscriptionActivated(msg.sender, subscriptionExpiry[msg.sender]);
        emit PaymentReceived(msg.sender, msg.value, "subscription");
    }

    function consumeCredit(address user) external onlyTreasury {
        require(credits[user] > 0, "No credits");
        credits[user]--;
        emit CreditsConsumed(user, credits[user]);
    }

    function hasAccess(address user) external view returns (bool) {
        return subscriptionExpiry[user] > block.timestamp || credits[user] > 0;
    }

    function isSubscribed(address user) external view returns (bool) {
        return subscriptionExpiry[user] > block.timestamp;
    }

    /// @notice Sets the per-signal price (wei).
    /// @dev    Rejects zero to prevent the `payPerSignal()` division-by-zero
    ///         DoS reported in the 2026-04-26 contracts review.
    /// @param  price New per-signal price in wei. Must be greater than zero.
    function setPricePerSignal(uint256 price) external onlyTreasury {
        require(price > 0, "Zero price");
        pricePerSignal = price;
    }

    /// @notice Sets the 30-day subscription price (wei).
    /// @dev    Rejects zero to prevent the "anyone subscribes for free" bug
    ///         reported in the 2026-04-26 contracts review (with
    ///         `monthlySubscription = 0`, `require(msg.value >= 0)` is
    ///         trivially satisfied).
    /// @param  price New monthly subscription price in wei. Must be greater than zero.
    function setMonthlySubscription(uint256 price) external onlyTreasury {
        require(price > 0, "Zero price");
        monthlySubscription = price;
    }

    function withdraw() external onlyTreasury {
        payable(treasury).transfer(address(this).balance);
    }

    /// @notice Nominates `newTreasury` as the pending treasury.
    /// @dev    Step 1 of the two-step transfer. The current treasury stays in
    ///         place until `newTreasury` calls `acceptTreasury()`. Calling this
    ///         with a different address before acceptance overwrites the
    ///         pending nominee. Zero address is rejected.
    /// @param  newTreasury The address to nominate as the next treasury. Must
    ///         not be the zero address.
    function transferTreasury(address newTreasury) external onlyTreasury {
        require(newTreasury != address(0), "Zero address");
        pendingTreasury = newTreasury;
        emit TreasuryTransferStarted(treasury, newTreasury);
    }

    /// @notice Finalises a pending treasury transfer initiated by `transferTreasury`.
    /// @dev    Step 2 of the two-step transfer. Must be called by the address
    ///         previously passed to `transferTreasury`. Clears `pendingTreasury`
    ///         on success. This guards against typos and transfers to addresses
    ///         whose private key is unknown (e.g. an unfunded multisig) — if
    ///         the new treasury cannot sign `acceptTreasury`, the role stays
    ///         with the existing treasury.
    function acceptTreasury() external {
        require(msg.sender == pendingTreasury, "Not pending treasury");
        address previousTreasury = treasury;
        treasury = pendingTreasury;
        pendingTreasury = address(0);
        emit TreasuryTransferred(previousTreasury, treasury);
    }
}
