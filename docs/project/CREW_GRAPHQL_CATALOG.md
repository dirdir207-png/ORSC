# Crew GraphQL Operation & Mutation Catalog (verified via mitmproxy)

Captured 2026-09-07 from the live native Crew app (`com.trycrew.crew`, React
Native/Expo v2.2.7) by routing its HTTPS traffic through mitmproxy (trusted CA)
and capturing every GraphQL operation/response. This is the AUTHORITATIVE write +
read contract set for Meridian bi-directional wiring — no invented mutations.

Method: system proxy Wi-Fi -> 127.0.0.1:8899 (mitmdump 12.2.3 via `uv
--python 3.11`, CA trusted in system keychain); quit + relaunch Crew.app;
drive via cliclick. Log: `/tmp/mitm-capture.log`.

## Mutations (15) — exact input contracts
Values redacted to shapes; ids are opaque base64.

### Bills
- `CreateBill` `{input{accountId,name,amount(¢),frequency,anchorDate,frequencyInterval,reassignmentRule{match,transactionType,debitCardId}}}`
- `ArchiveBill` `{input{billId}}` (bill delete/archive)
- `TopUpReserve` `{input{billReserveId,amount,subaccountId}}`
- `CreatePaycheckFundingPlan` `{input{billReserveId,name,amount,frequency,frequencyInterval,anchorDate,reassignmentRule{match}}}`
- `UpdatePaycheckFundingPlan` `{input{fundingPlanId,name,amount,frequency,frequencyInterval,anchorDate,reassignmentRule}}`
- `DeletePaycheckFundingPlan` `{input{fundingPlanId}}`
### Pockets
- `CreateSubaccount` `{input{accountId,type,name,initialTransferAmount,targetAmount,piggyBanked}}`
- `DeleteSubaccount` `{input{subaccountId}}`
- `InitiateTransferRuth` `{input{accountFromId,accountToId,amount,memo}}` (spend-pocket / internal transfer)
- `CreatePocketReassignmentRule` `{input{match,accountId,assignmentSubaccountId,minAmount,maxAmount}}`
- `DeletePocketReassignmentRule` `{input{reassignmentRuleId}}`
### Autopilot rules
- `CreateAutopilotRule` `{input{name,paused,formula{name,triggers,conditions.and.conditions[idMatch{entityId,entitySchema}],actions[sweepExcess{subaccountId,amountToRemain,sweepDestinations[{type,accountId,subaccountId,percentage}]}]}}}`
- `DeleteRule` `{input{ruleId}}`
### Other
- `RecordRiskSession` `{input{sessionId,installId,capturedAt,deviceLanguage,osName,osVersion,appName,appVersion,screenWidthPx,screenHeightPx,screenDensity,userAgent,deviceModel,deviceManufacturer,cpuArchs,totalStorageBytes,unusedStorageBytes,batteryLevel,batteryCharging,timezone,timezoneOffsetMinutes,connectionType,carrierName,isEmulator,isSimulator,debugBuild}}`
- `GenerateViewSadToken` `{input{debitCardId}}`

## Autopilot rule-action catalog (complete — NOT just sweep/roundUp)
`formula.actions` types:
- `RoundUpTransferAction` `{roundToNearest,accountId,subaccountId,memo}`
- `TargetBalanceTransferAction` `{target,direction,accountId,subaccountId}`
- `SplitDepositAction` `{destinations[{percentage,type,accountId,subaccountId}]}`
- `SplitDepositByAmountAction` `{surplusAccountId,destinations[{amount,type,accountId,subaccountId}]}`
- `InternalTransferAction` `{amount,accountFromId,accountToId,memo}`
- `SendNotificationAction` `{message,method,userIds}`
- `SendWebhookAction` `{url}`
- `sweepExcess` `{subaccountId,amountToRemain,sweepDestinations[{type,accountId,subaccountId,percentage}]}`

`conditions`: `IdMatchCondition` / `OrCondition` / `AndCondition`, each
`{entityId,entitySchema,type}`.
`triggers` (examples): `ACCOUNT_DEPOSIT_RECEIVED`, `DEBIT_CARD_TRANSACTION`.
Rule fields: `id,name,isPaused,isBroken,priority,formula{description,triggers,conditions,actions}`.

## Key read ops + fields (schema)
- **Card surface**: `CardTile` (activeCreditCard/activePhysicalCard/activePhysicalDebitCard/issuingCreditCard/issuingPhysicalCard/issuingPhysicalDebitCard/creditCardOrders/cardOrders/physicalDebitCardOrders/currentCreditCardOrder/currentCardOrder/currentPhysicalDebitCardOrder/**virtualDebitCards**/family/creditAccount/flags/permittedActions/debitCardOrder/debitCard); `PhysicalCards`; `FamilyDebitCards`; `AvailableCardColors`
- **Virtual cards**: `VirtualDebitCards` (currentUser/spendAccount/family/**virtualDebitCards**/subaccount); `VirtualDebitCardDetailScreen` (debitCardId/currentUser/debitCard/node/id/subaccount/owner/primaryOwner/account/subaccounts/primarySubaccount/family/address/bill/user/permittedActions/userSpendConfig/selectedSpendSubaccount); `VirtualCardCreationEligibility` (currentUser/permittedActions)
- **Autopilot rule node**: `AutopilotRuleNode` (ruleId/rule/node/id/formula/requiredEntityId/numericComparisonOp/numericComparisonValue/stringComparisonOp/stringComparisonValue/conditions/destinations/splitDepositByAmountDestinations/sourceSubaccountId/sweepDestinations/actions); `AutopilotRuleIds`; `AutopilotTile`; `AutopilotTabBadge`
- **Bill reserve**: `BillReserveDetails` (date/currentUser/spendAccount/billReserve/reassignmentRule/debitCard/firstUpcomingPayment/firstLatePayment/lastPayment/status/bill/settings/funding/subaccount/bills/billPayments/currentMonth/future/paidBillPayments); `BillReserveSettingsScreen` (activeFundingPlans/fundingPlans/settings/funding/surplusSubaccount); `BillReserveBottomSheet`, `BillReserveCalendarTile`, `BillReservePausedTile`, `BillReservePreviewScreen`, `BillReserveRecalculating`
- **Accounts/pockets**: `SubaccountsWithSettings`; `AccountsTile` (types SPENDING/SAVINGS/BILL_RESERVE/CREDIT_RESERVE); `AccountOverviewTile`; `AccountDetailsScreen`; `SubaccountNode`; `SubaccountDetail`; `SubaccountListTile`; `SubaccountAssociations`; `PocketAllocationsScreen`; `PocketAssignmentNode`; `PocketAssignmentRulesRuth`; `SmartBankingReassignmentRules`; `PocketDropdown`
- **Budget**: `BudgetScreen`, `BudgetIncomeScreen`, `AccountOwnerAllowance`
- **Funding**: `PaycheckFundingPlanDetails`; `FundingEventHistory`; `PendingTransfersToAccountOrSubaccount`
- **Bills txn**: `BillTransactionAssignmentList`; `BillTransactionHistory`; `BillPreviewTransactions`; `PaycheckTransactionAssignmentList`; `BillHistory`; `BillIdentificationCards`; `BillEligibleVirtualCards`; `SkipBillPaymentPrompt`; `SkipContributionDialog`
- **Identity/onboarding**: `UserApplication`; `IdentityVerification`; `ExternalAccounts`; `FamilyUsers`; `FamilyHasFunded`; `FamilyAllowances`; `FamilyCreditEligibility`; `FamilyDashboard`

## Key corrections to ORSC `crew_commands.py`
1. `create_autopilot_rule` uses ONLY `roundUpTransfer` — WRONG. Must support the full
   action-type union (see rule-action catalog); real captured action was `sweepExcess`.
2. `update_bill` reassignmentRule has `transactionType` + `debitCardId` fields.
3. `CreateAutopilotRule` real mutation shape is `formula.conditions.and.conditions`
   + `actions[{sweepExcess}]`, not the ORSC `roundUpTransfer` shape.
4. `UpdatePaycheckFundingPlan` amount:166400 = $1,664 = owner's guaranteed base paycheck.

## Full operation field catalog (durable)

Each op -> its captured field names (from the live app, authoritative).

- `AccountDetailsScreen`: id, date, currentUser, user, node, spendAccount, saveAccount, family, monthlyBonusAprBps, parents, users, creditAccount, owners, authorizedUsers, owner
- `AccountInterestDetails`: accountId, account, node, id, interestDetails, boostDetails
- `AccountOrSubaccountNode`: id, currentUser, node, subaccounts, account, owner, primarySubaccount, primaryOwner
- `AccountOverviewTile`: accountId, currentUser, spendAccount, billReserve, account, node, id, interestDetails, transfersTo, first, searchFilters, status, edges, transfersFrom, owner, primaryOwner, primarySubaccount, boostDetails, accountFrom, accountTo, subaccountFrom, subaccountTo, permittedActions
- `AccountOwnerAllowance`: id, node, primaryOwner, scheduledAllowance, destinations, account, pendingTransfers, subaccount, owner, accountFrom, accountTo, subaccountFrom, subaccountTo, permittedActions
- `AccountScreenBalanceTile`: accountId, account, node, id, simpleBalanceOverTime, interestDetails, primarySubaccount, boostDetails
- `AccountUserInfo`: accountId, currentUser, account, node, id, primaryOwner, userSpendConfig, selectedSpendSubaccount
- `AccountsTile`: id, types, currentUser, flags, user, node, userSpendConfig, selectedSpendSubaccount, spendAccount, billReserve, transfersTo, first, transfersFrom, primarySubaccount, subaccounts, account, permittedActions
- `ActiveUserTakeover`: currentUser, saveAccount
- `ActivityList`: accountId, cursor, pageSize, searchFilters, account, node, id, primarySubaccount, cashTransactions, first, after, pageInfo, edges, pendingCheckDeposits, owner, primaryOwner, accountFrom, accountTo, subaccountFrom, subaccountTo, permittedActions, subaccount, relatedTransactions, transfer, pendingTransfers, checkDeposit, manualHold
- `AllAccounts`: currentUser, spendAccount, subaccounts, saveAccount, family, signerSpendAccount, primarySubaccount, externalAccounts, parents, children, scheduledAllowance, destinations, account, subaccount, roles, owner, primaryOwner
- `AutopilotPlanOverview`: date, currentUser, spendAccount, billReserve, activeFundingPlans, allocations, reassignmentRule, debitCard, firstUpcomingPayment, firstLatePayment, lastPayment, status, bill, settings, funding, subaccount, bills, billPayments, currentMonth, future, paidBillPayments
- `AutopilotRuleIds`: currentUser, family, rules, flags
- `AutopilotRuleNode`: ruleId, rule, node, id, formula, requiredEntityId, numericComparisonOp, numericComparisonValue, stringComparisonOp, stringComparisonValue, conditions, destinations, splitDepositByAmountDestinations, sourceSubaccountId, sweepDestinations, actions
- `AutopilotTabBadge`: currentUser, spendAccount, billReserve
- `AutopilotTile`: currentUser, family, rules, flags
- `AvailableCardColors`: availableCardColors
- `BankingScreenRuth`: platform, currentUser, intercomJwt, flags, family, spendAccount, saveAccount, scheduledAllowance, permittedActions, owner, destinations, account, subaccount
- `BillDetailsScreen`: billId, date, bill, node, id, daysOverdue, reservedBy, firstUpcomingPayment, firstLatePayment, reassignmentRule, debitCard, user, billReserve, bills, settings, funding, subaccount, permittedActions
- `BillEligibleVirtualCards`: billId, currentUser, flags, virtualDebitCards, bill, node, id, virtualDebitCard
- `BillHistory`: billId, startDate, date, bill, node, id, expandedHistory, groupedHistoricPayments, totalSpentYtd, averageTransactionAmount
- `BillIdentificationCards`: currentUser, spendAccount, physicalDebitCards, virtualDebitCards, family, users, activeCreditCard, activePhysicalCard, type, user
- `BillPreviewTransactions`: accountId, frequency, anchorDate, frequencyInterval, searchFilters, account, node, id, billPreviewTransactions, owner, primaryOwner, subaccount, relatedTransactions, transfer, permittedActions, checkDeposit, manualHold
- `BillReserveBottomSheet`: currentUser, spendAccount, billReserve, settings, funding, subaccount, archivedBills
- `BillReserveCalendarTile`: date, currentUser, spendAccount, billReserve, reassignmentRule, debitCard, firstUpcomingPayment, firstLatePayment, lastPayment, status, bill, settings, funding, subaccount, bills, billPayments, currentMonth, future, paidBillPayments
- `BillReserveDetails`: date, currentUser, spendAccount, billReserve, reassignmentRule, debitCard, firstUpcomingPayment, firstLatePayment, lastPayment, status, bill, settings, funding, subaccount, bills, billPayments, currentMonth, future, paidBillPayments
- `BillReservePausedTile`: currentUser, spendAccount, billReserve, pausedBills
- `BillReservePreviewScreen`: currentUser, spendAccount, billReserve, bills, settings, funding, subaccount
- `BillReserveRecalculating`: currentUser, spendAccount, billReserve
- `BillReserveSettingsScreen`: currentUser, spendAccount, subaccounts, billReserve, bills, activeFundingPlans, fundingPlans, settings, funding, subaccount, surplusSubaccount, reassignmentRule
- `BillTransactionAssignmentList`: pageSize, cursor, searchFilters, currentUser, spendAccount, billReserve, assignableCashTransactions, first, after, pageInfo, edges, node, owner, account, primaryOwner, subaccount, relatedTransactions, transfer, permittedActions, checkDeposit, manualHold
- `BillTransactionHistory`: billId, bill, node, id, expandedHistory, recentCashTransactions, owner, account, primaryOwner, subaccount, relatedTransactions, transfer, permittedActions, checkDeposit, manualHold
- `Birthday`: id, node
- `BudgetIncomeScreen`: currentUser, spendAccount, billReserve, settings, funding, subaccount, bills, allocations, activeFundingPlans, fundingEvents, paycheckFundingPlans, reassignmentRule, cashTransaction, fundingPlan
- `BudgetScreen`: currentUser, flags, spendAccount, billReserve, activeFundingPlans
- `CardDeclinesTab`: userId, cursor, pageSize, searchFilters, user, node, id, cashTransactionDeclines, first, after, pageInfo, edges, subaccount
- `CardFilter`: accountId, account, node, id, physicalDebitCards, virtualDebitCards, user
- `CardTile`: userId, node, id, spendAccount, activeCreditCard, activePhysicalCard, type, activePhysicalDebitCard, issuingCreditCard, issuingPhysicalCard, issuingPhysicalDebitCard, creditCardOrders, cardOrders, physicalDebitCardOrders, currentCreditCardOrder, currentCardOrder, currentPhysicalDebitCardOrder, virtualDebitCards, family, creditAccount, flags, permittedActions, debitCardOrder, debitCard
- `CashDepositFees`: cashDepositFees
- `CashTransactionDeclines`: accountId, cursor, pageSize, searchFilters, account, node, id, cashTransactionDeclines, first, after, pageInfo, edges, subaccount
- `CheckDepositDetails`: checkDepositDetails
- `CreateBillScreen`: cashTransactionId, cashTransaction, node, id, account, debitCard
- `CreditCardBalanceTileEligibility`: currentUser, family, creditAccount
- `DebitCardEligibility`: subjectUserId, user, node, id, family, issuingPhysicalDebitCard, issuingPhysicalCard, type, activePhysicalDebitCard, activePhysicalCard, flags
- `DebitCardName`: debitCardId, debitCard, node, id, user
- `DebitCardNode`: id, node
- `DebitCardOrder`: type, currentUser, address, flags, family, children, parents, mailingAddress, spendAccount, creditAccount, activePhysicalCard, issuingPhysicalCard, currentCardOrder, permittedActions
- `DebitCardPocketSelector`: userId, accountId, user, node, id, activeCreditCard, activePhysicalCard, type, activePhysicalDebitCard, account, subaccounts, primarySubaccount, userSpendConfig, selectedSpendSubaccount
- `DebitCardPreviewScreen`: userId, user, node, id, spendAccount, family, creditAccount
- `EditDebitCardPinScreen`: id, node, activePhysicalDebitCard, activePhysicalCard, type, issuingPhysicalDebitCard, issuingPhysicalCard, virtualDebitCards
- `EntityNode`: id, node, primarySubaccount, user, owner, account, primaryOwner
- `ExternalAccounts`: currentUser, family, externalAccounts, institution, owner
- `FamilyAllowances`: currentUser, family, children, scheduledAllowance
- `FamilyCreditEligibility`: currentUser, family, permittedActions
- `FamilyDashboard`: currentUser, family, children, spendAccount, subaccounts, saveAccount, scheduledAllowance, parents, permittedActions, flags, owner, primarySubaccount, account, destinations, subaccount
- `FamilyDebitCards`: currentUser, family, users, activePhysicalDebitCard, activePhysicalCard, type, activeCreditCard, virtualDebitCards, user
- `FamilyHasFunded`: currentUser, family
- `FamilyUsers`: currentUser, family, users
- `FundingEventHistory`: cursor, pageSize, currentUser, spendAccount, billReserve, fundingEvents, first, after, pageInfo, edges, node, cashTransaction, fundingPlan
- `FuturePayments`: currentUser, family, scheduledPayments, destinations, account, recipient
- `HomeTabs`: currentUser, family, children, flags
- `IntercomToken`: platform, currentUser, intercomJwt
- `ListPeerRecipients`: currentUser, family, peerRecipientAccounts, transfersTo, first, searchFilters, status, edges, node, owner, account, primaryOwner, primarySubaccount, accountFrom, accountTo, subaccountFrom, subaccountTo, permittedActions
- `MenuScreen`: currentUser, family, children, parents, externalAccounts
- `MerchantFilterTransactions`: searchText, types, positiveOnly, currentUser, family, merchantFilterTransactions
- `PaycheckFundingPlanDetails`: id, fundingPlan, node, account, billReserve, reassignmentRule, sourceSubaccount
- `PaycheckTransactionAssignmentList`: pageSize, cursor, searchFilters, currentUser, spendAccount, billReserve, assignablePaycheckTransactions, first, after, pageInfo, edges, node, owner, account, primaryOwner, subaccount, relatedTransactions, transfer, permittedActions, checkDeposit, manualHold
- `PendingTransfersToAccountOrSubaccount`: accountOrSubaccountId, accountOrSubaccount, node, id, pendingTransfers, owner, account, primaryOwner, accountFrom, accountTo, subaccountFrom, subaccountTo, permittedActions
- `PhysicalCards`: currentUser, family, children, spendAccount, activeCreditCard, activePhysicalCard, type, activePhysicalDebitCard, issuingCreditCard, issuingPhysicalCard, permittedActions, debitCardOrder, issuingPhysicalDebitCard, parents, user, userSpendConfig, selectedSpendSubaccount
- `PocketAllocationsScreen`: currentUser, spendAccount, billReserve, allocations, targetAccount, targetSubaccount, owner
- `PocketAssignmentNode`: pocketAssignmentId, rule, node, id, owner, account, permittedActions, assignmentSubaccount
- `PocketAssignmentRulesRuth`: currentUser, spendAccount, primarySubaccount, family, accounts, primaryOwner, reassignmentRules, children, owner, account, permittedActions, assignmentSubaccount
- `PocketDropdown`: accountId, currentUser, account, node, id, subaccounts, permittedActions
- `ReserveBalanceOverviewTile`: currentUser, spendAccount, billReserve, nextFundingPlan, nextFundingEvent, activeFundingPlans, fundingEvents, allocations, bills, projectedNsfPayment, bill, settings, funding, subaccount, permittedActions, creditReserve, stagingSubaccount, reassignmentRule, cashTransaction, fundingPlan
- `ReserveBalanceTile`: currentUser, spendAccount, billReserve, upcomingPayments, bill
- `ReserveDetailsScreen`: date, currentUser, spendAccount, billReserve, allocations, upcomingPayments, bill, reassignmentRule, debitCard, firstUpcomingPayment, firstLatePayment, lastPayment, status, settings, funding, subaccount, bills, billPayments, currentMonth, future, paidBillPayments
- `SettingsScreen`: currentUser, family, parents, userSettings
- `SingleAccountDetails`: id, node, primarySubaccount, boostDetails, institution, interestDetails, authorizedUsers, owners, family, beneficiary, owner
- `SkipBillPaymentPrompt`: billId, date, bill, node, id, firstLatePayment, firstUpcomingPayment
- `SkipContributionDialog`: fundingPlanId, fundingPlan, node, id
- `SmartBankingReassignmentRules`: currentUser, spendAccount, family, users, subaccounts, reassignmentRules, owner, account, permittedActions, assignmentSubaccount
- `SubaccountAssociations`: subaccountId, currentUser, spendAccount, billReserve, subaccount, node, id, account, associations, reassignmentRules, rules, virtualDebitCards, allocations
- `SubaccountDetail`: subaccountId, currentUser, subaccount, node, id, account, subaccounts, simpleBalanceOverTime, owner, permittedActions
- `SubaccountFilter`: accountId, account, node, id, subaccounts, primarySubaccount, billReserve, stagingSubaccount, bills
- `SubaccountListTile`: accountId, types, currentUser, flags, family, parents, account, node, id, primarySubaccount, subaccounts, primaryOwner, permittedActions, owner, userSpendConfig, selectedSpendSubaccount
- `SubaccountNode`: subaccountId, subaccount, node, id, owner, account
- `SubaccountsWithSettings`: accountOrUserId, types, accountOrUser, node, id, billReserve, subaccounts, owner, simpleBalanceOverTime, spendAccount, account, permittedActions
- `TransactionUpdatesPoller`: currentUser, family
- `UserApplication`: applicationType, currentUser, hasConsentedToESign, hasConsentedTo, document, externalAccounts, family, flags, currentUserApplication, type, identityVerification
- `UserPrompts`: currentUser, prompts, permittedActions, target
- `UserTracking`: currentUser, family, flags, userSettingEnabled, setting
- `VirtualCardCreationEligibility`: currentUser, permittedActions
- `VirtualDebitCardDetailScreen`: debitCardId, currentUser, debitCard, node, id, subaccount, owner, primaryOwner, account, subaccounts, primarySubaccount, family, address, bill, user, permittedActions, userSpendConfig, selectedSpendSubaccount
- `VirtualDebitCards`: currentUser, spendAccount, family, virtualDebitCards, subaccount