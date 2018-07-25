# Setting up the Vagrant environment

1. Install Vagrant and Virtualbox
1. Make sure virtualisation is enabled in your BIOS settings
1. Create the file `./ansible/aws/credentials` with the following content:
   ```
   [default-long-term]
   aws_access_key_id = <your_access_key>
   aws_secret_access_key = <your_secret_key>
   aws_mfa_device=arn:aws:iam::887689817172:mfa/<your_iam_username>
   ```
1. Create the file `./ansible/authorized_keys/<your_ssh_username>.azk` containing your SSH public key in 'authorized keys' format.
1. Open a terminal, navigate to this directory and run `vagrant --port-ssuffix=11 up`
1. Wait for the box to boot
1. Run `ssh ubuntu@localhost -p 2211` to SSH into your new box
1. Run `aws-mfa` and input your MFA passcode to authenticate your session.