import { PrismaClient, UserRole } from '@prisma/client';
import bcrypt from 'bcryptjs';

const prisma = new PrismaClient();

const PASSWORD = 'Admin@123';
const SALT_ROUNDS = 12;

const roles = [
  {
    name: UserRole.ADMIN,
    description: 'System Administrator',
  },
  {
    name: UserRole.GOVERNMENT,
    description: 'Government Authority',
  },
  {
    name: UserRole.RECYCLER,
    description: 'Authorized Recycler',
  },
  {
    name: UserRole.COLLECTOR,
    description: 'Collection Partner',
  },
  {
    name: UserRole.CONSUMER,
    description: 'End Consumer',
  },
] as const;

const users = [
  {
    fullName: 'System Administrator',
    email: 'admin@ecotrace.com',
    phone: '9999999991',
    region: 'Head Office',
    role: UserRole.ADMIN,
  },
  {
    fullName: 'Government Officer',
    email: 'government@ecotrace.com',
    phone: '9999999992',
    region: 'Tamil Nadu',
    role: UserRole.GOVERNMENT,
  },
  {
    fullName: 'Collection Partner',
    email: 'collector@ecotrace.com',
    phone: '9999999993',
    region: 'Chennai',
    role: UserRole.COLLECTOR,
  },
  {
    fullName: 'Authorized Recycler',
    email: 'recycler@ecotrace.com',
    phone: '9999999994',
    region: 'Chennai',
    role: UserRole.RECYCLER,
  },
  {
    fullName: 'Demo Consumer',
    email: 'consumer@ecotrace.com',
    phone: '9999999995',
    region: 'Chennai',
    role: UserRole.CONSUMER,
  },
] as const;

async function main(): Promise<void> {
  console.log('🌱 Seeding EcoTrace database...\n');

  // Seed Roles
  for (const role of roles) {
    await prisma.role.upsert({
      where: { name: role.name },
      update: {
        description: role.description,
      },
      create: {
        name: role.name,
        description: role.description,
      },
    });
  }

  console.log('✅ Roles seeded.');

  const passwordHash = await bcrypt.hash(PASSWORD, SALT_ROUNDS);

  // Seed Users
  for (const user of users) {
    const role = await prisma.role.findUnique({
      where: {
        name: user.role,
      },
    });

    if (!role) {
      throw new Error(`Role ${user.role} not found.`);
    }

    await prisma.user.upsert({
      where: {
        email: user.email,
      },
      update: {
        fullName: user.fullName,
        phone: user.phone,
        region: user.region,
        roleId: role.id,
        isActive: true,
      },
      create: {
        fullName: user.fullName,
        email: user.email,
        passwordHash,
        phone: user.phone,
        region: user.region,
        roleId: role.id,
        isActive: true,
        emailVerified: true,
      },
    });

    console.log(`✅ ${user.role} user seeded.`);
  }

  console.log('\n🎉 EcoTrace database seeded successfully!');
  console.log('\nDemo Accounts');
  console.log('==============================');

  users.forEach((user) => {
    console.log(`${user.role}`);
    console.log(`Email    : ${user.email}`);
    console.log(`Password : ${PASSWORD}\n`);
  });
}

main()
  .catch((error) => {
    console.error(error);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
