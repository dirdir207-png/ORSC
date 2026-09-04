"""Exact Crew GraphQL documents shared by command adapters and broker."""

CREATE_SUBACCOUNT_MUTATION = """mutation CreateSubaccount($input: CreateSubaccountInput!) {
  createSubaccount(input: $input) {
    result { id name balance goal status subaccountType }
  }
}"""

DELETE_SUBACCOUNT_MUTATION = """mutation DeleteSubaccount($id: ID!) {
  deleteSubaccount(input: { subaccountId: $id }) {
    result { id name status }
  }
}"""

SET_SPEND_POCKET_MUTATION = """mutation SetActiveSpendPocketScottie($input: SetSpendSubaccountInput!) {
  setSpendSubaccount(input: $input) {
    result { id userSpendConfig { id selectedSpendSubaccount { id clearedBalance } } }
  }
}"""

UPDATE_VIRTUAL_CARD_MUTATION = """mutation UpdateVirtualDebitCard($input: UpdateVirtualDebitCardInput!) {
  updateVirtualDebitCard(input: $input) {
    result { id subaccount { id displayName } }
  }
}"""
