import { PrismaClient, UserRole } from '@prisma/client';

const prisma = new PrismaClient();

/**
 * Fixed system roles for EcoTrace India.
 *
 * These map 1:1 to the UserRole enum defined in schema.prisma and are the
 * canonical source for RBAC.
 *
 * Seeding is idempotent:
 * - Existing roles are updated with the latest description.
 * - Missing roles are created.
 * - Duplicate roles are never inserted.
 */
const roles = Object.freeze([
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
] as const);

async function main(): Promise<void> {
  for (const role of roles) {
    await prisma.role.upsert({
      where: {
        name: role.name,
      },
      update: {
        description: role.description,
      },
      create: {
        name: role.name,
        description: role.description,
      },
    });
  }

  console.log(`✅ Successfully seeded ${roles.length} system roles.`);
}

main()
  .catch((error) => {
    console.error('❌ Database seeding failed.');
    console.error(error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
