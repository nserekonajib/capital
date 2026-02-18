from pay import PayClass

callPay = PayClass.momopay("1000", "EUR", "1234TEST", "+256760671063", 'DONATE FOR WEEK')
print(callPay["response"])
print(callPay['ref'])

verify = PayClass.verifymomo(callPay['ref'])
print(verify)


checkcollectionbalance = PayClass.momobalance()
print(checkcollectionbalance)

withdraw = PayClass.withdrawmtnmomo("25", "EUR", "1234TEST", "+256760671063", "Withdraw for personal use")
print(withdraw)



