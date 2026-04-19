// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract SapphirePaymentGate {
    address public treasury;
    mapping(address => uint256) public credits;
    mapping(address => uint256) public subscriptionExpiry;

    uint256 public pricePerSignal = 0.001 ether;    // ~$0.003
    uint256 public monthlySubscription = 0.1 ether; // ~$300

    event PaymentReceived(address indexed from, uint256 amount, string service);
    event SubscriptionActivated(address indexed subscriber, uint256 expiry);
    event CreditsConsumed(address indexed user, uint256 remaining);

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

    function setPricePerSignal(uint256 price) external onlyTreasury {
        pricePerSignal = price;
    }

    function setMonthlySubscription(uint256 price) external onlyTreasury {
        monthlySubscription = price;
    }

    function withdraw() external onlyTreasury {
        payable(treasury).transfer(address(this).balance);
    }

    function transferTreasury(address newTreasury) external onlyTreasury {
        require(newTreasury != address(0), "Zero address");
        treasury = newTreasury;
    }
}
