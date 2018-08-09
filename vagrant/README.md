# Setting up the development environment

1. Install Docker on your linux machine
1. Create the file `./ansible/aws/credentials` with the following content:
   ```
   [default-long-term]
   aws_access_key_id = <your_access_key>
   aws_secret_access_key = <your_secret_key>
   aws_mfa_device=arn:aws:iam::887689817172:mfa/<your_iam_username>
   ```
1. Run the command:
   ```
   docker run \
       -v ../..:/vagrant \
       -w /vagrant/infrastructure/vagrant \
       --name biometrixtech-build \
       -u root \
       geerlingguy/docker-ubuntu1804-ansible:latest \
       ansible-playbook ansible/main.yml -c local \
   && docker commit \
       -c 'CMD ["ssh-agen", "bash"]' \
       biometrixtech-build \
       biometrixtech:latest \
   && docker rm biometrixtech-build
   ```
   To build a new docker image for the development environment
1. Run the command:
   ```
   docker run \
       -v ../..:/vagrant \
       -v /path/to/your/ssh/keys:/root/auth \
       -it \
       --name biometrixtech \
       -u root \
       biometrixtech:latest
   ```
   To launch a new container and give you a bash prompt inside it.
1. Run `ssh-add /root/auth/your_key.pem` to add your SSH key for Git pushes
1. Run `aws-mfa` and input your MFA passcode to authenticate your session.