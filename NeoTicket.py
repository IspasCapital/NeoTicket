from typing import Any, Union, cast

from boa3.builtin.compile_time import NeoMetadata, metadata, public
from boa3.builtin.contract import Nep17TransferEvent, abort
from boa3.builtin.interop import runtime, storage
from boa3.builtin.interop.blockchain import Transaction, get_contract, get_transaction
from boa3.builtin.interop.runtime import script_container
from boa3.builtin.interop.contract import GAS as GAS_SCRIPT, NEO as NEO_SCRIPT, call_contract
from boa3.builtin.nativecontract.neo import NEO as NEO_TOKEN
from boa3.builtin.nativecontract.contractmanagement import ContractManagement
from boa3.builtin.type import UInt160, ECPoint, ByteString


# -------------------------------------------
# METADATA
# -------------------------------------------

@metadata
def manifest_metadata() -> NeoMetadata:
    """
    Defines this smart contract's metadata information
    """
    meta = NeoMetadata()
    meta.supported_standards = ['NEP-17']
    meta.add_permission(methods=['onNEP17Payment','update'])
    meta.add_permission(contract='0xef4073a0f2b305a38ec4050e4d3d28bc40ea63f5')

    meta.author = "N/A"
    meta.description = "NeoTicket"
    meta.email = "N/A"
    return meta


# -------------------------------------------
# TOKEN SETTINGS
# -------------------------------------------


OWNER = UInt160('NPtQK1RrR4FEJ7VCZ6pgGXa1C7dMbRi6UV'.to_script_hash())
SUPPLY_KEY = 'totalSupply'

# Symbol of the Token
TOKEN_SYMBOL = 'NeoTicket'

# Number of decimal places
TOKEN_DECIMALS = 0

# Total Supply of tokens in the system
TOKEN_TOTAL_SUPPLY = 10_000_000

# Total Supply of tokens in the system
TOKEN_MAX_SUPPLY = 100_000_000

# -------------------------------------------
# Events
# -------------------------------------------

on_transfer = Nep17TransferEvent

# -------------------------------------------
# Methods
# -------------------------------------------

@public
def update(nef_file: bytes, manifest: bytes, data: Any = None):
    """
    Updates the smart contract.
    """
    if runtime.check_witness(OWNER):
        ContractManagement.update(nef_file, manifest, data)

@public
def voting_candidates() -> list:
    """
    Returns list of voting candidates in the format List[Tuple[ECPoint, int]]
    """
    return NEO_TOKEN.get_candidates()

@public
def vote_for_candidate(from_address: UInt160, vote_to: ECPoint) -> bool:
    """
    Votes for a candidate
    """
    if NEO_TOKEN.vote(from_address,vote_to):
        return True
    else:
        return False

@public(safe=True)
def symbol() -> str:
    """
    Gets the symbols of the token.

    This string must be valid ASCII, must not contain whitespace or control characters, should be limited to uppercase
    Latin alphabet (i.e. the 26 letters used in English) and should be short (3-8 characters is recommended).
    This method must always return the same value every time it is invoked.

    :return: a short string representing symbol of the token managed in this contract.
    """
    return TOKEN_SYMBOL


@public(safe=True)
def decimals() -> int:
    """
    Gets the amount of decimals used by the token.

    E.g. 8, means to divide the token amount by 100,000,000 (10 ^ 8) to get its user representation.
    This method must always return the same value every time it is invoked.

    :return: the number of decimals used by the token.
    """
    return TOKEN_DECIMALS


@public(name='totalSupply', safe=True)
def total_supply() -> int:
    """
    Gets the total token supply deployed in the system.

    This number must not be in its user representation. E.g. if the total supply is 10,000,000 tokens, this method
    must return 10,000,000 * 10 ^ decimals.

    :return: the total token supply deployed in the system.
    """
    return storage.get(SUPPLY_KEY).to_int()


@public(name='balanceOf', safe=True)
def balance_of(account: UInt160) -> int:
    """
    Get the current balance of an address

    The parameter account must be a 20-byte address represented by a UInt160.

    :param account: the account address to retrieve the balance for
    :type account: UInt160
    """
    assert len(account) == 20
    return storage.get(account).to_int()


@public
def transfer(from_address: UInt160, to_address: UInt160, amount: int, data: Any) -> bool:
    """
    Transfers an amount of NEP17 tokens from one account to another

    If the method succeeds, it must fire the `Transfer` event and must return true, even if the amount is 0,
    or from and to are the same address.

    :param from_address: the address to transfer from
    :type from_address: UInt160
    :param to_address: the address to transfer to
    :type to_address: UInt160
    :param amount: the amount of NEP17 tokens to transfer
    :type amount: int
    :param data: whatever data is pertinent to the onPayment method
    :type data: Any

    :return: whether the transfer was successful
    :raise AssertionError: raised if `from_address` or `to_address` length is not 20 or if `amount` is less than zero.
    """
    # the parameters from and to should be 20-byte addresses. If not, this method should throw an exception.
    assert len(from_address) == 20 and len(to_address) == 20
    # the parameter amount must be greater than or equal to 0. If not, this method should throw an exception.
    assert amount >= 0

    # The function MUST return false if the from account balance does not have enough tokens to spend.
    from_balance = storage.get(from_address).to_int()
    if from_balance < amount:
        return False

    # The function should check whether the from address equals the caller contract hash.
    # If so, the transfer should be processed;
    # If not, the function should use the check_witness to verify the transfer.
    if from_address != runtime.calling_script_hash:
        if not runtime.check_witness(from_address):
            return False

    # skip balance changes if transferring to yourself or transferring 0 cryptocurrency
    if from_address != to_address and amount != 0:
        if from_balance == amount:
            storage.delete(from_address)
        else:
            storage.put(from_address, from_balance - amount)

        to_balance = storage.get(to_address).to_int()
        storage.put(to_address, to_balance + amount)

    # if the method succeeds, it must fire the transfer event
    on_transfer(from_address, to_address, amount)
    # if the to_address is a smart contract, it must call the contracts onPayment
    post_transfer(from_address, to_address, amount, data)
    # and then it must return true
    return True


def post_transfer(from_address: Union[UInt160, None], to_address: Union[UInt160, None], amount: int, data: Any):
    """
    Checks if the one receiving NEP17 tokens is a smart contract and if it's one the onPayment method will be called

    :param from_address: the address of the sender
    :type from_address: UInt160
    :param to_address: the address of the receiver
    :type to_address: UInt160
    :param amount: the amount of cryptocurrency that is being sent
    :type amount: int
    :param data: any pertinent data that might validate the transaction
    :type data: Any
    """
    if to_address is not None:
        contract = ContractManagement.get_contract(to_address)
        if contract is not None:
            call_contract(to_address, 'onNEP17Payment', [from_address, amount, data])


def mint(account: UInt160, amount: int):
    """
    Mints new tokens. This is not a NEP-17 standard method, it's only being use to complement the onPayment method

    :param account: the address of the account that is sending cryptocurrency to this contract
    :type account: UInt160
    :param amount: the amount of Neo to be refunded
    :type amount: int
    :raise AssertionError: raised if amount is less than than 0
    """
    assert amount >= 0
    if amount != 0:
        current_total_supply = total_supply()
        account_balance = balance_of(account)

        if current_total_supply + amount <= TOKEN_MAX_SUPPLY:
            storage.put(SUPPLY_KEY, current_total_supply + amount)
            storage.put(account, account_balance + amount)

            on_transfer(None, account, amount)
            post_transfer(None, account, amount, None)
        else:
            abort()

@public
def burn(account: UInt160, amount: int):
    """
    Burns NeoTicket tokens.

    :param account: the address of the account that is pulling out cryptocurrency of this contract
    :type account: UInt160
    :param amount: the amount of Neo to be refunded
    :type amount: int
    :raise AssertionError: raised if `account` length is not 20, amount is less than than 0 or the account doesn't have
    enough NeoTicket to burn
    """
    assert len(account) == 20
    assert amount >= 0
    if runtime.check_witness(account):
        if amount != 0:
            current_total_supply = total_supply()
            account_balance = balance_of(account)

            assert account_balance >= amount

            storage.put(SUPPLY_KEY, current_total_supply - amount)

            if account_balance == amount:
                storage.delete(account)
            else:
                storage.put(account, account_balance - amount)

            on_transfer(account, None, amount)
            post_transfer(account, None, amount, None)

            NEO_TOKEN.transfer(runtime.executing_script_hash, account, amount,None)
            
@public
def verify() -> bool:
    """
    When this contract address is included in the transaction signature,
    this method will be triggered as a VerificationTrigger to verify that the signature is correct.
    For example, this method needs to be called when withdrawing token from the contract.

    :return: whether the transaction signature is correct
    """
    return runtime.check_witness(OWNER)


@public
def _deploy(data: Any, update: bool):
    """
    Initializes the storage when the smart contract is deployed.

    :return: whether the deploy was successful. This method must return True only during the smart contract's deploy.
    """
    if not update:
        storage.put(SUPPLY_KEY, TOKEN_TOTAL_SUPPLY)
        storage.put(OWNER, TOKEN_TOTAL_SUPPLY)

        on_transfer(None, OWNER, TOKEN_TOTAL_SUPPLY)


@public
def onNEP17Payment(from_address: UInt160, amount: int, data: Any):
    """
    :param from_address: the address of the one who is trying to send cryptocurrency to this smart contract
    :type from_address: UInt160
    :param amount: the amount of cryptocurrency that is being sent to the this smart contract
    :type amount: int
    :param data: any pertinent data that might validate the transaction
    :type data: Any
    """

    # Use calling_script_hash if NEO is transfered to the contract
    if runtime.calling_script_hash == NEO_SCRIPT:
        mint(from_address, amount)
    elif runtime.calling_script_hash == GAS_SCRIPT:
        return
    else:
        abort()

