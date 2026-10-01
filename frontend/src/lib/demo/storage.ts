import { IDS, daysAgo, hoursAgo } from './shared'

/** Standalone storage files — `/v1/storage/files`. */
export const demoStorageFiles = {
  files: [
    {
      id: IDS.storageBoardDeck,
      fileName: 'q3-board-deck.pdf',
      contentType: 'application/pdf',
      sizeBytes: 4_820_411,
      status: 'ready',
      key: `storage/demo/${IDS.storageBoardDeck}/q3-board-deck.pdf`,
      createdAt: daysAgo(11),
      updatedAt: daysAgo(11),
    },
    {
      id: IDS.storageFeatureCsv,
      fileName: 'feature-requests.csv',
      contentType: 'text/csv',
      sizeBytes: 214_882,
      status: 'ready',
      key: `storage/demo/${IDS.storageFeatureCsv}/feature-requests.csv`,
      createdAt: daysAgo(6),
      updatedAt: daysAgo(6),
    },
    {
      id: IDS.storageBrand,
      fileName: 'brand-guidelines.md',
      contentType: 'text/markdown',
      sizeBytes: 18_204,
      status: 'ready',
      key: `storage/demo/${IDS.storageBrand}/brand-guidelines.md`,
      createdAt: hoursAgo(20),
      updatedAt: hoursAgo(20),
    },
  ],
  usage: {
    fileCount: 3,
    storageBytes: 5_053_497,
    limits: { maxFiles: 10, maxFileBytes: 31_457_280, maxStorageBytes: 104_857_600 },
  },
}
